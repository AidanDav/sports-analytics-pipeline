import logging
from datetime import datetime, timezone, date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.team import Team
from app.models.game import Game
from app.models.player import Player
from app.models.ingestion_run import IngestionRun
from app.ingestion.cfbd_client import CFBDClient


logger = logging.getLogger(__name__)
KEPT_CLASSIFICATIONS = ("fbs", "fcs")


class CFBDIngestionService:
    """Handles ingestion logic: mapping, upserting, and logging runs."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.client = CFBDClient()

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