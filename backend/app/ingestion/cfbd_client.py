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
        """Fetch all FBS teams."""
        logger.info("Fetching teams from CFBD")
        return await self._get("/teams", params={"division": "fbs"})

    async def get_games(self, year: int, season_type: str = "regular") -> list[dict]:
        """Fetch games for a given year and season type."""
        logger.info(f"Fetching {season_type} games for {year} from CFBD")
        return await self._get(
            "/games", params={"year": year, "seasonType": season_type}
        )

    async def get_roster(self, team: str, year: int) -> list[dict]:
            """Fetch roster for a specific team and year."""
            logger.info(f"Fetching {year} roster for {team} from CFBD")
            return await self._get(
                "/roster", params={"team": team, "year": year}
            )