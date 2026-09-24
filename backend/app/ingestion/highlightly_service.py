import logging
from datetime import datetime, timezone, date, timedelta

from sqlalchemy import select, exists
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.team import Team
from app.models.game import Game
from app.models.player import Player
from app.models.player_stats import PlayerStats
from app.models.ingestion_run import IngestionRun
from app.ingestion.highlightly_client import HighlightlyClient

logger = logging.getLogger(__name__)


class HighlightlyIngestionService:
    """Handles ingestion logic for Highlightly API data.
    
    The core normalization challenge: Highlightly returns NFL data in a
    completely different shape than CFBD returns college data. This service
    maps both into the same unified schema.
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.client = HighlightlyClient()

    async def ingest_teams(self, league: str = "NFL") -> IngestionRun:
        """Fetch teams from Highlightly and upsert into the database.
        
        Key mapping differences from CFBD:
        - CFBD uses "school" for the name, Highlightly uses "displayName"
        - CFBD includes conference, Highlightly does not
        - Highlightly returns "NFL" uppercase, we store "nfl" lowercase
        """
        run = IngestionRun(
            source="highlightly",
            data_type="teams",
            status="running",
        )
        self.db.add(run)
        await self.db.flush()

        try:
            raw_teams = await self.client.get_teams(league=league)
            created = 0
            updated = 0
            skipped = 0

            for raw in raw_teams:
                external_id = str(raw["id"])

                # Skip All-Star / conference placeholder teams
                # (Highlightly includes AFC and NFC as "teams")
                if raw.get("name") in ("AFC", "NFC"):
                    skipped += 1
                    continue

                result = await self.db.execute(
                    select(Team).where(
                        Team.source == "highlightly",
                        Team.external_id == external_id,
                    )
                )
                existing = result.scalar_one_or_none()

                if existing:
                    # displayName is the full name like "Kansas City Chiefs"
                    existing.name = raw.get("displayName", existing.name)
                    existing.abbreviation = raw.get("abbreviation", existing.abbreviation)
                    updated += 1
                else:
                    team = Team(
                        source="highlightly",
                        external_id=external_id,
                        league=league.lower(),
                        name=raw.get("displayName", "Unknown"),
                        abbreviation=raw.get("abbreviation"),
                        # Highlightly doesn't provide conference at the team level
                        conference=None,
                    )
                    self.db.add(team)
                    created += 1

            await self.db.flush()
            run.status = "success"
            run.rows_created = created
            run.rows_updated = updated
            run.rows_skipped = skipped
            run.completed_at = datetime.now(timezone.utc)

            logger.info(
                f"Highlightly team ingestion complete: {created} created, "
                f"{updated} updated, {skipped} skipped"
            )

        except Exception as e:
            run.status = "failed"
            run.error_message = str(e)
            run.completed_at = datetime.now(timezone.utc)
            logger.error(f"Highlightly team ingestion failed: {e}")

        return run

    def _parse_score(self, score_string: str) -> tuple[int | None, int | None]:
        """Parse Highlightly's score format '21 - 7' into two integers.
        
        This is a key normalization step. CFBD gives us homePoints and
        awayPoints as integers. Highlightly gives us a single string
        like '21 - 7' that we need to split and convert.

        Unplayed games can come back with a null score, so None is
        handled explicitly instead of letting .split() raise and take
        down the whole ingestion run.
        """
        if not score_string:
            return None, None
        try:
            parts = score_string.split(" - ")
            return int(parts[0]), int(parts[1])
        except (ValueError, IndexError):
            return None, None

    def _map_status(self, description: str | None) -> str:
        """Map Highlightly's status descriptions to our internal statuses.
        
        Highlightly uses: 'Finished', 'Scheduled', 'In progress', etc.
        Our schema uses: 'final', 'scheduled', 'in_progress'
        """
        if not description:
            return "scheduled"
        mapping = {
            "Finished": "final",
            "Scheduled": "scheduled",
            "In progress": "in_progress",
            "Half time": "in_progress",
            "End period": "in_progress",
            "Postponed": "postponed",
            "Cancelled": "cancelled",
            "Suspended": "suspended",
            "Abandoned": "abandoned",
        }
        return mapping.get(description, "scheduled")

    # Statuses where the game hasn't kicked off. Highlightly sends "0 - 0"
    # for these, which would otherwise be stored as a real 0-0 score.
    UNPLAYED_STATUSES = {"scheduled", "postponed", "cancelled"}

    @staticmethod
    def _parse_date(raw_date: str | None) -> date | None:
        """Parse the UTC date portion of an ISO timestamp like '2026-10-23T00:15:00.000Z'."""
        if not raw_date:
            return None
        try:
            return date.fromisoformat(raw_date[:10])
        except ValueError:
            return None
 
    @staticmethod
    def _season_anchor(raw_matches: list[dict]) -> date | None:
        """Find the Wednesday that starts Week 1 of the regular season.
 
        Highlightly's round field is just "preseason" or "regular-season"
        with no week number, so weeks are derived from dates. The anchor
        comes from the data itself (earliest regular-season game), so
        nothing is hardcoded per season.
 
        Why Wednesday: dates are UTC, so Monday Night Football (8:15 PM ET)
        is stored as Tuesday. A Tuesday boundary would push every MNF game
        into the following week. No regular NFL week starts on a Wednesday
        in UTC, and the occasional Wednesday game (Christmas 2024) belongs
        to the week it opens, which a Wednesday boundary also gets right.
        """
        dates = [
            HighlightlyIngestionService._parse_date(m.get("date"))
            for m in raw_matches
            if m.get("round") == "regular-season"
        ]
        dates = [d for d in dates if d]
        if not dates:
            return None
        first = min(dates)
        # weekday(): Monday=0 ... Wednesday=2. Step back to the Wednesday
        # on or before the first game.
        return first - timedelta(days=(first.weekday() - 2) % 7)
 
    @staticmethod
    def _week_number(
        round_str: str | None, game_date: date | None, anchor: date | None
    ) -> int | None:
        """Week number for a regular-season game, None for anything else."""
        if round_str != "regular-season" or not game_date or not anchor:
            return None
        days = (game_date - anchor).days
        if days < 0:
            return None
        return days // 7 + 1

    def _infer_position(self, statistics: list[dict]) -> str | None:
        """Infer a player's position from their stat groups.
        
        Highlightly box scores don't include position, but the stat
        categories tell us what role a player filled in that game.
        """
        groups = {s.get("group", "").lower() for s in statistics}

        if "passing" in groups:
            return "QB"
        if "rushing" in groups and "receiving" not in groups:
            return "RB"
        if "receiving" in groups:
            return "WR"
        if "defense" in groups:
            return "DEF"
        if "kicking" in groups or "punting" in groups:
            return "K"
        return None


    async def ingest_matches(self, season: int, league: str = "NFL") -> IngestionRun:
        """Fetch matches from Highlightly and upsert into the database.
        
        Key mapping differences from CFBD:
        - CFBD gives homePoints/awayPoints as integers,
          Highlightly gives state.score.current as '21 - 7'
        - CFBD gives team names as strings,
          Highlightly nests full team objects with their own IDs
        - CFBD uses a 'completed' boolean,
          Highlightly uses state.description with multiple status values
        """
        run = IngestionRun(
            source="highlightly",
            data_type="games",
            status="running",
        )
        self.db.add(run)
        await self.db.flush()

        try:
            # Matches endpoint returns paginated: {"data": [...], "pagination": {...}}
            raw_matches = await self.client.get_matches(season=season, league=league)
            # Computed once from the full season payload, used for every match
            anchor = self._season_anchor(raw_matches)
            created = 0
            updated = 0
            skipped = 0

            # Build lookup of Highlightly external_id -> our internal team id
            result = await self.db.execute(
                select(Team).where(Team.source == "highlightly")
            )
            teams = result.scalars().all()
            team_lookup = {team.external_id: team.id for team in teams}

            for raw in raw_matches:
                external_id = str(raw["id"])
                result = await self.db.execute(
                    select(Game).where(
                        Game.source == "highlightly",
                        Game.external_id == external_id,
                    )
                )
                existing = result.scalar_one_or_none()

                # Resolve nested team objects to our internal IDs
                home_ext_id = str(raw.get("homeTeam", {}).get("id", ""))
                away_ext_id = str(raw.get("awayTeam", {}).get("id", ""))
                home_team_id = team_lookup.get(home_ext_id)
                away_team_id = team_lookup.get(away_ext_id)

                # Parse the score string into integers
                # `or {}` rather than a .get default: the default only applies
                # when the key is missing, not when the API sends null
                state = raw.get("state") or {}
                score_str = (state.get("score") or {}).get("current")
                home_score, away_score = self._parse_score(score_str)

                # Map Highlightly status to our internal status
                status = self._map_status(state.get("description"))

                # Unplayed games come back as "0 - 0". Store no score rather
                # than a fake 0-0 result.
                if status in self.UNPLAYED_STATUSES:
                    home_score, away_score = None, None

                game_date = self._parse_date(raw.get("date"))
                week = self._week_number(raw.get("round"), game_date, anchor)

                if existing:
                    existing.season = raw.get("season", existing.season)
                    existing.week = week
                    existing.home_team_id = home_team_id
                    existing.away_team_id = away_team_id
                    existing.home_score = home_score
                    existing.away_score = away_score
                    existing.game_date = game_date
                    existing.status = status
                    updated += 1
                else:
                    game = Game(
                        source="highlightly",
                        external_id=external_id,
                        league=league.lower(),
                        season=raw.get("season", season),
                        week=week,
                        home_team_id=home_team_id,
                        away_team_id=away_team_id,
                        home_score=home_score,
                        away_score=away_score,
                        game_date=game_date,
                        status=status,
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
                f"Highlightly match ingestion for {season} complete: "
                f"{created} created, {updated} updated, {skipped} skipped"
            )

        except Exception as e:
            run.status = "failed"
            run.error_message = str(e)
            run.completed_at = datetime.now(timezone.utc)
            logger.error(f"Highlightly match ingestion failed: {e}")

        return run

    def _split_name(self, full_name: str) -> tuple[str | None, str]:
        """Split 'Hudson Card' into ('Hudson', 'Card').
        
        Highlightly gives a single fullName string. Our schema
        stores first_name and last_name separately. We split on
        the first space and treat everything after as last name
        to handle names like 'Patrick Surtain II'.
        """
        parts = full_name.split(" ", 1)
        if len(parts) == 2:
            return parts[0], parts[1]
        return None, parts[0]

    def _map_stats(self, statistics: list[dict]) -> dict[str, dict]:
        """Map Highlightly's verbose stat entries to our flat schema.
        
        Highlightly returns stats as a list like:
            [{"group": "Passing", "name": "Total Passing Yards", "value": 273}, ...]
        
        We need to group by category and map to our column names:
            {"passing": {"yards": 273, "completions": 24, "attempts": 25, ...}}
        """
        categories = {}

        for stat in statistics:
            group = stat.get("group", "").lower()
            name = stat.get("name", "")
            value = stat.get("value")

            if value is None:
                continue

            # Initialize the category dict if needed
            if group not in categories:
                categories[group] = {"stat_category": group}

            entry = categories[group]

            # Map Highlightly stat names to our schema columns
            mapping = {
                "Total Passes": "attempts",
                "Total Successful Passes": "completions",
                "Total Passing Yards": "yards",
                "Total Passing Touchdowns": "touchdowns",
                "Total Passing Interceptions": "interceptions",
                "Total Rushing Attempts": "carries",
                "Total Rushing Yards": "yards",
                "Total Rushing Touchdowns": "touchdowns",
                "Total Receptions": "receptions",
                "Total Receiving Yards": "yards",
                "Total Receiving Touchdowns": "touchdowns",
                "Total Receiving Targets": "targets",
                "Total Fumbles": "fumbles",
                "Total Defensive Tackles": "tackles",
                "Total Defensive Sacks": "sacks",
            }

            column = mapping.get(name)
            if column:
                entry[column] = value

        return categories

    async def ingest_box_scores(self, limit: int | None = None) -> IngestionRun:
        """Fetch box scores for Highlightly matches and upsert players + stats.
        
        This does double duty: creates Player records from the box score
        player data, and creates PlayerStats records from their statistics.
        The limit parameter caps how many matches to process, important
        because each match is one API call and the free tier has daily limits.
        """
        run = IngestionRun(
            source="highlightly",
            data_type="players_and_stats",
            status="running",
        )
        self.db.add(run)
        await self.db.flush()

        try:
            # Only games we haven't pulled yet. Without this, every run
            # re-fetched the same first N games and never made progress.
            has_stats = exists().where(PlayerStats.game_id == Game.id)
            query = (
                select(Game)
                .where(
                    Game.source == "highlightly",
                    Game.status == "final",
                    ~has_stats,
                )
                # Newest first, so recent games fill in before old ones
                .order_by(Game.game_date.desc().nulls_last(), Game.id.desc())
            )
            if limit:
                query = query.limit(limit)

            matches = (await self.db.execute(query)).scalars().all()

            # Build team lookup: external_id -> internal id
            result = await self.db.execute(
                select(Team).where(Team.source == "highlightly")
            )
            teams = result.scalars().all()
            team_lookup = {team.external_id: team.id for team in teams}

            players_created = 0
            stats_created = 0
            skipped = 0

            for match in matches:
                try:
                    box_score = await self.client.get_box_score(
                        match_id=int(match.external_id)
                    )
                except Exception as e:
                    logger.warning(
                        f"Failed to fetch box score for match {match.external_id}: {e}"
                    )
                    skipped += 1
                    continue

                for team_data in box_score:
                    team_info = team_data.get("team", {})
                    team_ext_id = str(team_info.get("id", ""))
                    internal_team_id = team_lookup.get(team_ext_id)

                    for box in team_info.get("boxScores", []):
                        player_raw = box.get("player", {})
                        player_ext_id = str(player_raw.get("id", ""))
                        full_name = player_raw.get("name", "Unknown")
                        first_name, last_name = self._split_name(full_name)

                        # Upsert the player
                        result = await self.db.execute(
                            select(Player).where(
                                Player.source == "highlightly",
                                Player.external_id == player_ext_id,
                            )
                        )
                        player = result.scalar_one_or_none()

                        inferred_position = self._infer_position(box.get("statistics", []))

                        if not player:
                            player = Player(
                                source="highlightly",
                                external_id=player_ext_id,
                                league="nfl",
                                team_id=internal_team_id,
                                first_name=first_name,
                                last_name=last_name,
                                position=inferred_position,
                                number=player_raw.get("jersey"),
                            )
                            self.db.add(player)
                            await self.db.flush()
                            players_created += 1
                        else:
                            player.team_id = internal_team_id
                            player.number = player_raw.get("jersey", player.number)
                            # Only update position if we inferred one and they don't have one yet
                            if inferred_position and not player.position:
                                player.position = inferred_position
                     
                        # Map and insert stats by category (skip if already exists)
                        stat_categories = self._map_stats(
                            box.get("statistics", [])
                        )
                        for cat_data in stat_categories.values():
                            category = cat_data.pop("stat_category")
                            # Check for existing stat line for this player/game/category
                            existing_stat = await self.db.execute(
                                select(PlayerStats).where(
                                    PlayerStats.source == "highlightly",
                                    PlayerStats.player_id == player.id,
                                    PlayerStats.game_id == match.id,
                                    PlayerStats.stat_category == category,
                                )
                            )
                            if existing_stat.scalar_one_or_none():
                                skipped += 1
                                continue

                            stat = PlayerStats(
                                source="highlightly",
                                player_id=player.id,
                                game_id=match.id,
                                team_id=internal_team_id,
                                stat_category=category,
                                **cat_data,
                            )
                            self.db.add(stat)
                            stats_created += 1

                await self.db.flush()

            run.status = "success"
            run.rows_created = players_created + stats_created
            run.rows_updated = 0
            run.rows_skipped = skipped
            run.completed_at = datetime.now(timezone.utc)

            logger.info(
                f"Highlightly box score ingestion complete: "
                f"{players_created} players created, "
                f"{stats_created} stat rows created, {skipped} matches skipped"
            )

        except Exception as e:
            run.status = "failed"
            run.error_message = str(e)
            run.completed_at = datetime.now(timezone.utc)
            logger.error(f"Highlightly box score ingestion failed: {e}")

        return run