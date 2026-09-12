import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.team import Team
from app.models.game import Game
from app.models.ingestion_run import IngestionRun
from app.ingestion.cfbd_client import CFBDClient

logger = logging.getLogger(__name__)


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
                external_id = str(raw["id"])
                result = await self.db.execute(
                    select(Game).where(
                        Game.source == "cfbd",
                        Game.external_id == external_id,
                    )
                )
                existing = result.scalar_one_or_none()

                # Resolve team names to our internal IDs
                # If the team isn't in our database yet, we skip rather
                # than crash. This means teams should be ingested first.
                home_team_id = team_lookup.get(raw.get("home_team"))
                away_team_id = team_lookup.get(raw.get("away_team"))

                if existing:
                    existing.season = raw.get("season", existing.season)
                    existing.week = raw.get("week", existing.week)
                    existing.home_team_id = home_team_id
                    existing.away_team_id = away_team_id
                    existing.home_score = raw.get("home_points")
                    existing.away_score = raw.get("away_points")
                    existing.venue = raw.get("venue")
                    existing.status = "final" if raw.get("home_points") is not None else "scheduled"
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
                        home_score=raw.get("home_points"),
                        away_score=raw.get("away_points"),
                        game_date=raw.get("start_date", "")[:10] if raw.get("start_date") else None,
                        status="final" if raw.get("home_points") is not None else "scheduled",
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