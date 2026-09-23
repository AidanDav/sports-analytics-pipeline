import httpx
import logging

from app.core.config import settings

logger = logging.getLogger(__name__)


class CFBDClient:
    """Async HTTP client for the CollegeFootballData API."""

    BASE_URL = "https://api.collegefootballdata.com"

    def __init__(self):
        # Bearer token auth - CFBD expects this format
        self.headers = {
            "Authorization": f"Bearer {settings.cfbd_api_key}",
            "Accept": "application/json",
        }

    async def _get(self, endpoint: str, params: dict | None = None) -> list[dict]:
        """Make a GET request to the CFBD API.

        Creates a new AsyncClient per request. For ingestion jobs that
        run a few times a day, this is simpler than managing a
        persistent connection pool.
        """
        url = f"{self.BASE_URL}{endpoint}"
        async with httpx.AsyncClient() as client:
            response = await client.get(
                url, headers=self.headers, params=params, timeout=30.0
            )
            response.raise_for_status()
            return response.json()

    async def get_teams(self) -> list[dict]:
        """Fetch every team.

        /teams has no division filter (it silently ignored the old
        division=fbs param), so the service filters on each team's
        classification field instead.
        """
        logger.info("Fetching teams from CFBD")
        return await self._get("/teams")

    async def get_games(self, year: int, season_type: str = "regular") -> list[dict]:
        """Fetch games for a given year and season type."""
        logger.info(f"Fetching {season_type} games for {year} from CFBD")
        return await self._get(
            "/games", params={"year": year, "seasonType": season_type}
        )

    async def get_roster(self, year: int, classification: str) -> list[dict]:
        """Fetch every roster in one classification ("fbs" or "fcs").

        With no team param, one call returns every team's roster.
        """
        logger.info(f"Fetching {year} {classification} rosters from CFBD")
        return await self._get(
            "/roster", params={"year": year, "classification": classification}
        )