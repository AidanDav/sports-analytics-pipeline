import httpx
import logging

from app.core.config import settings

logger = logging.getLogger(__name__)


class HighlightlyClient:
    """Async HTTP client for the Highlightly American Football API."""

    BASE_URL = "https://american-football.highlightly.net"

    def __init__(self):
        # Highlightly uses x-rapidapi-key header instead of Bearer token
        self.headers = {
            "x-rapidapi-key": settings.highlightly_api_key,
            "Accept": "application/json",
        }

    async def _get(self, endpoint: str, params: dict | None = None) -> list | dict:
        """Make a GET request to the Highlightly API."""
        url = f"{self.BASE_URL}{endpoint}"
        async with httpx.AsyncClient() as client:
            response = await client.get(
                url, headers=self.headers, params=params, timeout=30.0
            )
            response.raise_for_status()
            return response.json()

    async def get_teams(self, league: str = "NFL") -> list[dict]:
        """Fetch all teams for a given league."""
        logger.info(f"Fetching {league} teams from Highlightly")
        return await self._get("/teams", params={"league": league})

    async def get_matches(self, season: int, league: str = "NFL") -> list[dict]:
        """Fetch all matches for a given season, handling pagination.
    
        Highlightly caps at 100 results per request, so we loop
        with increasing offset until we've collected everything.
        """
        logger.info(f"Fetching {league} matches for {season} from Highlightly")
        all_matches = []
        offset = 0
        limit = 100

        while True:
            response = await self._get(
                "/matches",
                params={
                    "season": season,
                    "league": league,
                    "limit": limit,
                    "offset": offset,
                },
            )
            batch = response.get("data", [])
            all_matches.extend(batch)

            total = response.get("pagination", {}).get("totalCount", 0)
            if offset + limit >= total or not batch:
                break
            offset += limit

        logger.info(f"Fetched {len(all_matches)} total matches for {season}")
        return all_matches

   
    async def get_players(self, limit: int = 1000, offset: int = 0) -> dict:
        """Fetch players. Returns paginated response."""
        logger.info(f"Fetching players from Highlightly (offset={offset})")
        return await self._get(
            "/players", params={"limit": limit, "offset": offset}
        )

    async def get_player_details(self, player_id: int) -> list[dict]:
        """Fetch detailed player profile by ID."""
        logger.info(f"Fetching player {player_id} details from Highlightly")
        return await self._get(f"/players/{player_id}")

    async def get_box_score(self, match_id: int) -> list[dict]:
        """Fetch per-player box scores for a specific match."""
        logger.info(f"Fetching box score for match {match_id} from Highlightly")
        return await self._get(f"/box-score/{match_id}")