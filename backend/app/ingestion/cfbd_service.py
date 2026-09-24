import logging
from datetime import datetime, timezone, date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.team import Team
from app.models.game import Game
from app.models.player import Player
from app.models.player_stats import PlayerStats
from app.models.ingestion_run import IngestionRun
from app.ingestion.cfbd_client import CFBDClient


logger = logging.getLogger(__name__)
KEPT_CLASSIFICATIONS = ("fbs", "fcs")

# CFBD box score category -> (our stat_category, {CFBD stat type: our column}).
# C/ATT is handled separately because it holds two numbers.
CFBD_STAT_MAP = {
    "passing": ("passing", {"YDS": "yards", "TD": "touchdowns", "INT": "interceptions"}),
    "rushing": ("rushing", {"CAR": "carries", "YDS": "yards", "TD": "touchdowns"}),
    "receiving": ("receiving", {"REC": "receptions", "YDS": "yards", "TD": "touchdowns"}),
    "defensive": ("defense", {"TOT": "tackles", "SACKS": "sacks"}),
}

# Columns stored as floats in PlayerStats. Everything else is an int.
FLOAT_COLUMNS = {"yards", "tackles", "sacks"}

class CFBDIngestionService:
    """Handles ingestion logic: mapping, upserting, and logging runs."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.client = CFBDClient()

    @staticmethod
    def _to_number(raw, cast):
        """CFBD sends stat values as strings. Returns None for blanks or "--"."""
        try:
            return cast(float(raw))
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _split_name(full_name: str) -> tuple[str | None, str]:
        """Split "Ollie Gordon II" into ("Ollie", "Gordon II")."""
        first, _, last = full_name.strip().partition(" ")
        if not last:
            return None, first or "Unknown"
        return first, last

    def _pivot_team_stats(self, categories: list[dict]) -> dict[tuple[str, str], dict]:
        """Turn CFBD's category -> stat type -> athletes nesting into one
        line per player per category.

        Returns {(athlete_id, stat_category): {"name": ..., column: value}}.
        """
        lines: dict[tuple[str, str], dict] = {}

        for cat in categories:
            mapping = CFBD_STAT_MAP.get(cat.get("name"))
            if not mapping:
                # Kicking, punting, returns: no matching columns
                continue
            category, columns = mapping

            for stat_type in cat.get("types", []):
                type_name = stat_type.get("name")

                for athlete in stat_type.get("athletes", []):
                    athlete_id = str(athlete.get("id", ""))
                    name = (athlete.get("name") or "").strip()
                    # Team-total rows aren't real players
                    if not athlete_id or athlete_id.startswith("-") or name.lower() == "team":
                        continue

                    line = lines.setdefault((athlete_id, category), {"name": name})
                    raw = athlete.get("stat")

                    if type_name == "C/ATT":
                        comp, _, att = str(raw).partition("/")
                        line["completions"] = self._to_number(comp, int)
                        line["attempts"] = self._to_number(att, int)
                    elif type_name in columns:
                        column = columns[type_name]
                        cast = float if column in FLOAT_COLUMNS else int
                        line[column] = self._to_number(raw, cast)

        return lines

    async def ingest_teams(self) -> IngestionRun:
        """Fetch teams from CFBD and upsert into the database."""
        # Step 1: Log the start of this run
        run = IngestionRun(
            source="cfbd",
            data_type="teams",
            status="running",
        )
        self.db.add(run)
        await self.db.flush()

        try:
            # Step 2: Fetch raw data from the API
            raw_teams = await self.client.get_teams()
            created = 0
            updated = 0
            skipped = 0
            
            for raw in raw_teams:
                classification = raw.get("classification")
                if classification not in KEPT_CLASSIFICATIONS:
                    skipped += 1
                    continue

                # Step 3: Check if this team already exists (upsert logic)
                external_id = str(raw["id"])
                result = await self.db.execute(
                    select(Team).where(
                        Team.source == "cfbd",
                        Team.external_id == external_id,
                    )
                )
                existing = result.scalar_one_or_none()

                if existing:
                    # Update fields that might have changed
                    existing.name = raw.get("school", existing.name)
                    existing.abbreviation = raw.get("abbreviation", existing.abbreviation)
                    existing.conference = raw.get("conference", existing.conference)
                    existing.classification = classification
                    updated += 1
                else:
                    # Create a new team record
                    team = Team(
                        source="cfbd",
                        external_id=external_id,
                        league="cfb",
                        name=raw.get("school", "Unknown"),
                        abbreviation=raw.get("abbreviation"),
                        conference=raw.get("conference"),
                        classification=classification,
                    )
                    self.db.add(team)
                    created += 1

            # Step 4: Commit all changes and mark the run as successful
            await self.db.flush()
            run.status = "success"
            run.rows_created = created
            run.rows_updated = updated
            run.rows_skipped = skipped
            run.completed_at = datetime.now(timezone.utc)

            logger.info(
                f"CFBD team ingestion complete: {created} created, "
                f"{updated} updated, {skipped} skipped"
            )

        except Exception as e:
            run.status = "failed"
            run.error_message = str(e)
            run.completed_at = datetime.now(timezone.utc)
            logger.error(f"CFBD team ingestion failed: {e}")

        return run

    async def ingest_games(self, year: int) -> IngestionRun:
        """Fetch games for a given year from CFBD and upsert into the database."""
        run = IngestionRun(
            source="cfbd",
            data_type="games",
            status="running",
        )
        self.db.add(run)
        await self.db.flush()

        try:
            raw_games = await self.client.get_games(year=year)
            created = 0
            updated = 0
            skipped = 0

            # Build a lookup dict of team name -> team id so we don't
            # query the database for every single game row
            result = await self.db.execute(
                select(Team).where(Team.source == "cfbd")
            )
            teams = result.scalars().all()
            team_lookup = {team.name: team.id for team in teams}

            for raw in raw_games:
                if (
                    raw.get("homeClassification") not in KEPT_CLASSIFICATIONS
                    or raw.get("awayClassification") not in KEPT_CLASSIFICATIONS
                ):
                    skipped += 1
                    continue
                external_id = str(raw["id"])
                result = await self.db.execute(
                    select(Game).where(
                        Game.source == "cfbd",
                        Game.external_id == external_id,
                    )
                )
                existing = result.scalar_one_or_none()

                # Resolve team names to our internal IDs
                # If the team isn't in our database yet, the ID will be None
                home_team_id = team_lookup.get(raw.get("homeTeam"))
                away_team_id = team_lookup.get(raw.get("awayTeam"))

                # Determine game status from the completed flag
                status = "final" if raw.get("completed") else "scheduled"

                # Parse the date from the ISO timestamp
                raw_date = raw.get("startDate")
                game_date = date.fromisoformat(raw_date[:10]) if raw_date else None

                if existing:
                    existing.season = raw.get("season", existing.season)
                    existing.week = raw.get("week", existing.week)
                    existing.home_team_id = home_team_id
                    existing.away_team_id = away_team_id
                    existing.home_score = raw.get("homePoints")
                    existing.away_score = raw.get("awayPoints")
                    existing.game_date = game_date
                    existing.venue = raw.get("venue")
                    existing.status = status
                    updated += 1
                else:
                    game = Game(
                        source="cfbd",
                        external_id=external_id,
                        league="cfb",
                        season=raw.get("season", year),
                        week=raw.get("week"),
                        home_team_id=home_team_id,
                        away_team_id=away_team_id,
                        home_score=raw.get("homePoints"),
                        away_score=raw.get("awayPoints"),
                        game_date=game_date,
                        status=status,
                        venue=raw.get("venue"),
                    )
                    self.db.add(game)
                    created += 1

            await self.db.flush()
            run.status = "success"
            run.rows_created = created
            run.rows_updated = updated
            run.rows_skipped = skipped
            run.completed_at = datetime.now(timezone.utc)

            logger.info(
                f"CFBD game ingestion for {year} complete: {created} created, "
                f"{updated} updated, {skipped} skipped"
            )

        except Exception as e:
            run.status = "failed"
            run.error_message = str(e)
            run.completed_at = datetime.now(timezone.utc)
            logger.error(f"CFBD game ingestion failed: {e}")

        return run

    async def ingest_players(self, year: int) -> IngestionRun:
        """Fetch every FBS and FCS roster and upsert players.

        /roster accepts a classification with no team, so this is two
        API calls total instead of one per team. Players are matched to
        our teams by the roster's team name.
        """
        run = IngestionRun(source="cfbd", data_type="players", status="running")
        self.db.add(run)
        await self.db.flush()

        try:
            result = await self.db.execute(select(Team).where(Team.source == "cfbd"))
            team_lookup = {t.name: t.id for t in result.scalars().all()}

            # Load existing players once. Two classifications return tens
            # of thousands of players, and one query per player is far
            # too slow at that size.
            result = await self.db.execute(select(Player).where(Player.source == "cfbd"))
            players_by_ext_id = {p.external_id: p for p in result.scalars().all()}

            created = 0
            updated = 0
            skipped = 0
            unmatched_teams = set()

            for classification in KEPT_CLASSIFICATIONS:
                try:
                    raw_players = await self.client.get_roster(
                        year=year, classification=classification
                    )
                except Exception as e:
                    logger.warning(f"Failed to fetch {classification} rosters: {e}")
                    skipped += 1
                    continue

                for raw in raw_players:
                    team_id = team_lookup.get(raw.get("team"))
                    if team_id is None:
                        # CFBD data has name typos like "SacredHeart".
                        # Skipping beats attaching a player to a guess.
                        unmatched_teams.add(raw.get("team"))
                        skipped += 1
                        continue

                    external_id = str(raw["id"])
                    fields = {
                        "team_id": team_id,
                        "first_name": raw.get("firstName"),
                        "last_name": raw.get("lastName"),
                        "position": raw.get("position"),
                        "number": raw.get("jersey"),
                    }

                    player = players_by_ext_id.get(external_id)
                    if player:
                        # Only overwrite with real values, so a sparse
                        # entry can't erase a known position or number
                        for key, value in fields.items():
                            if value is not None:
                                setattr(player, key, value)
                        updated += 1
                    else:
                        fields["last_name"] = fields["last_name"] or "Unknown"
                        player = Player(
                            source="cfbd", external_id=external_id, league="cfb", **fields
                        )
                        self.db.add(player)
                        players_by_ext_id[external_id] = player
                        created += 1

            if unmatched_teams:
                logger.warning(
                    f"Roster teams not found in teams table: {sorted(unmatched_teams)}"
                )

            await self.db.flush()
            run.status = "success"
            run.rows_created = created
            run.rows_updated = updated
            run.rows_skipped = skipped
            run.completed_at = datetime.now(timezone.utc)
            logger.info(
                f"CFBD player ingestion for {year} complete: {created} created, "
                f"{updated} updated, {skipped} skipped"
            )

        except Exception as e:
            run.status = "failed"
            run.error_message = str(e)
            run.completed_at = datetime.now(timezone.utc)
            logger.error(f"CFBD player ingestion failed: {e}")

        return run

    async def ingest_game_stats(
        self, year: int, week: int, season_type: str = "regular"
    ) -> IngestionRun:
        """Fetch one week of CFB box scores and store player stat lines.

        Two API calls (FBS, FCS) cover every game that week. Players are
        matched to roster players by CFBD athlete ID. Anyone missing from
        the roster (walk-ons, late additions) is created on the spot.
        """
        run = IngestionRun(source="cfbd", data_type="stats", status="running")
        self.db.add(run)
        await self.db.flush()

        try:
            result = await self.db.execute(select(Team).where(Team.source == "cfbd"))
            team_lookup = {t.name: t.id for t in result.scalars().all()}

            result = await self.db.execute(select(Player).where(Player.source == "cfbd"))
            players_by_ext_id = {p.external_id: p for p in result.scalars().all()}

            players_created = 0
            stats_created = 0
            skipped = 0

            for classification in KEPT_CLASSIFICATIONS:
                try:
                    raw_games = await self.client.get_game_player_stats(
                        year=year, week=week,
                        classification=classification, season_type=season_type,
                    )
                except Exception as e:
                    logger.warning(
                        f"Failed to fetch {classification} stats for {year} week {week}: {e}"
                    )
                    skipped += 1
                    continue

                # Resolve every game in the payload with one query
                ext_ids = [str(g["id"]) for g in raw_games]
                result = await self.db.execute(
                    select(Game).where(Game.source == "cfbd", Game.external_id.in_(ext_ids))
                )
                games_by_ext_id = {g.external_id: g for g in result.scalars().all()}

                # Stat lines already stored for these games. FBS vs FCS
                # games come back in both calls, and reruns are common.
                game_ids = [g.id for g in games_by_ext_id.values()]
                result = await self.db.execute(
                    select(
                        PlayerStats.player_id, PlayerStats.game_id, PlayerStats.stat_category
                    ).where(PlayerStats.game_id.in_(game_ids))
                )
                existing = set(result.all())

                for raw_game in raw_games:
                    game = games_by_ext_id.get(str(raw_game["id"]))
                    if game is None:
                        # Not in our games table (D-II opponent, or games not synced)
                        skipped += 1
                        continue

                    for raw_team in raw_game.get("teams", []):
                        team_id = team_lookup.get(raw_team.get("team"))
                        if team_id is None:
                            skipped += 1
                            continue

                        lines = self._pivot_team_stats(raw_team.get("categories", []))

                        for (athlete_id, category), line in lines.items():
                            player = players_by_ext_id.get(athlete_id)
                            if player is None:
                                first, last = self._split_name(line["name"])
                                player = Player(
                                    source="cfbd", external_id=athlete_id, league="cfb",
                                    team_id=team_id, first_name=first, last_name=last,
                                )
                                self.db.add(player)
                                await self.db.flush()  # need player.id below
                                players_by_ext_id[athlete_id] = player
                                players_created += 1

                            key = (player.id, game.id, category)
                            if key in existing:
                                skipped += 1
                                continue

                            fields = {k: v for k, v in line.items() if k != "name"}
                            self.db.add(PlayerStats(
                                source="cfbd", player_id=player.id, game_id=game.id,
                                team_id=team_id, stat_category=category, **fields,
                            ))
                            existing.add(key)
                            stats_created += 1

            await self.db.flush()
            run.status = "success"
            run.rows_created = players_created + stats_created
            run.rows_updated = 0
            run.rows_skipped = skipped
            run.completed_at = datetime.now(timezone.utc)
            logger.info(
                f"CFBD stat ingestion for {year} week {week} complete: "
                f"{players_created} players created, {stats_created} stat lines created, "
                f"{skipped} skipped"
            )

        except Exception as e:
            run.status = "failed"
            run.error_message = str(e)
            run.completed_at = datetime.now(timezone.utc)
            logger.error(f"CFBD stat ingestion failed: {e}")

        return run