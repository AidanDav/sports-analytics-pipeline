import logging
from datetime import datetime, timezone, date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.team import Team
from app.models.game import Game
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
        """
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
                state = raw.get("state", {})
                score_str = state.get("score", {}).get("current", "")
                home_score, away_score = self._parse_score(score_str)

                # Map Highlightly status to our internal status
                status = self._map_status(state.get("description"))

                # Parse ISO date from the match
                raw_date = raw.get("date")
                game_date = None
                if raw_date:
                    try:
                        game_date = date.fromisoformat(raw_date[:10])
                    except ValueError:
                        pass

                # Parse round string to extract week number if possible
                # Highlightly uses "Regular Season - 5" format
                round_str = raw.get("round", "")
                week = None
                if " - " in round_str:
                    try:
                        week = int(round_str.split(" - ")[1])
                    except (ValueError, IndexError):
                        pass

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