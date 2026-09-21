"""Tests for the manual /ingestion/* trigger endpoints.

The service logic is covered in test_cfbd_service.py and
test_highlightly_service.py. Here the services are mocked so these
tests only check the route layer: correct method called with correct
arguments, and the IngestionRun mapped into the response schema.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

ROUTES = "app.api.routes.ingestion"


def _run(status="success", created=5, updated=2, error=None):
    return MagicMock(
        status=status, rows_created=created, rows_updated=updated,
        error_message=error,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("path, service, method, expected_kwargs", [
    ("/ingestion/cfbd/teams", "CFBDIngestionService", "ingest_teams", {}),
    ("/ingestion/cfbd/games?year=2023", "CFBDIngestionService", "ingest_games", {"year": 2023}),
    ("/ingestion/cfbd/players?year=2023", "CFBDIngestionService", "ingest_players", {"year": 2023}),
    ("/ingestion/highlightly/teams", "HighlightlyIngestionService", "ingest_teams", {"league": "NFL"}),
    ("/ingestion/highlightly/matches?season=2023", "HighlightlyIngestionService",
     "ingest_matches", {"season": 2023, "league": "NFL"}),
    ("/ingestion/highlightly/box-scores?limit=3", "HighlightlyIngestionService",
     "ingest_box_scores", {"limit": 3}),
])
async def test_ingestion_route_calls_service(client, path, service, method, expected_kwargs):
    with patch(f"{ROUTES}.{service}") as svc_cls:
        setattr(svc_cls.return_value, method, AsyncMock(return_value=_run()))
        response = await client.post(path)

    assert response.status_code == 200
    assert response.json() == {
        "status": "success", "rows_created": 5, "rows_updated": 2, "error": None,
    }
    getattr(svc_cls.return_value, method).assert_awaited_once_with(**expected_kwargs)


@pytest.mark.asyncio
async def test_ingestion_route_defaults(client):
    """Omitted query params should fall back to the 2024 season."""
    with patch(f"{ROUTES}.CFBDIngestionService") as svc_cls:
        svc_cls.return_value.ingest_games = AsyncMock(return_value=_run())
        await client.post("/ingestion/cfbd/games")

    svc_cls.return_value.ingest_games.assert_awaited_once_with(year=2024)


@pytest.mark.asyncio
async def test_ingestion_route_surfaces_failure(client):
    """A failed run still returns 200, with the error in the body."""
    with patch(f"{ROUTES}.HighlightlyIngestionService") as svc_cls:
        svc_cls.return_value.ingest_teams = AsyncMock(
            return_value=_run(status="failed", created=0, updated=0, error="401 Unauthorized")
        )
        response = await client.post("/ingestion/highlightly/teams")

    assert response.status_code == 200
    assert response.json()["status"] == "failed"
    assert response.json()["error"] == "401 Unauthorized"