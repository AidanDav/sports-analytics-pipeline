"""Tests for the raw HTTP clients.

The service tests mock the client entirely. These go one layer lower:
httpx.AsyncClient is swapped for one backed by httpx.MockTransport, so
the real request building (URLs, auth headers, query params) and the
Highlightly pagination loop execute, but no packet leaves the machine.
"""
from unittest.mock import patch

import httpx
import pytest

from app.ingestion.cfbd_client import CFBDClient
from app.ingestion.highlightly_client import HighlightlyClient

_RealAsyncClient = httpx.AsyncClient


def mock_http(handler):
    """Patch httpx.AsyncClient so every client instance routes to handler.

    Also returns a list that collects every request made, for assertions.
    """
    requests = []

    def recording_handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return handler(request)

    def factory(*args, **kwargs):
        return _RealAsyncClient(transport=httpx.MockTransport(recording_handler))

    return patch("httpx.AsyncClient", side_effect=factory), requests


# --- CFBD ---

@pytest.mark.asyncio
async def test_cfbd_sends_bearer_auth_and_params():
    patcher, requests = mock_http(lambda r: httpx.Response(200, json=[]))

    with patcher, patch("app.ingestion.cfbd_client.settings.cfbd_api_key", "test-key"):
        await CFBDClient().get_games(year=2024)

    req = requests[0]
    assert req.url.path == "/games"
    assert req.url.params["year"] == "2024"
    assert req.url.params["seasonType"] == "regular"
    assert req.headers["Authorization"] == "Bearer test-key"


@pytest.mark.asyncio
async def test_cfbd_teams_sends_no_division_filter():
    patcher, requests = mock_http(lambda r: httpx.Response(200, json=[{"id": 1}]))

    with patcher:
        result = await CFBDClient().get_teams()

    assert result == [{"id": 1}]
    assert requests[0].url.path == "/teams"
    assert "division" not in requests[0].url.params


@pytest.mark.asyncio
async def test_cfbd_roster_by_classification():
    patcher, requests = mock_http(lambda r: httpx.Response(200, json=[]))

    with patcher:
        await CFBDClient().get_roster(year=2026, classification="fcs")

    params = requests[0].url.params
    assert requests[0].url.path == "/roster"
    assert params["classification"] == "fcs"
    assert params["year"] == "2026"
    assert "team" not in params

@pytest.mark.asyncio
async def test_cfbd_game_player_stats_params():
    patcher, requests = mock_http(lambda r: httpx.Response(200, json=[]))

    with patcher:
        await CFBDClient().get_game_player_stats(year=2026, week=3, classification="fbs")

    params = requests[0].url.params
    assert requests[0].url.path == "/games/players"
    assert params["year"] == "2026"
    assert params["week"] == "3"
    assert params["classification"] == "fbs"
    assert params["seasonType"] == "regular"

@pytest.mark.asyncio
async def test_cfbd_http_error_propagates():
    """The client raises; the service is responsible for catching it."""
    patcher, _ = mock_http(lambda r: httpx.Response(401, json={"error": "bad key"}))

    with patcher, pytest.raises(httpx.HTTPStatusError):
        await CFBDClient().get_teams()


# --- Highlightly ---

@pytest.mark.asyncio
async def test_highlightly_sends_rapidapi_header():
    patcher, requests = mock_http(lambda r: httpx.Response(200, json=[]))

    with patcher, patch(
        "app.ingestion.highlightly_client.settings.highlightly_api_key", "hl-key"
    ):
        await HighlightlyClient().get_teams(league="NFL")

    assert requests[0].headers["x-rapidapi-key"] == "hl-key"
    assert "Authorization" not in requests[0].headers


@pytest.mark.asyncio
async def test_highlightly_matches_paginates_until_total():
    """Regression for the Day 4 bug where only the first 100 of 335
    matches came back. 250 total at limit 100 should take 3 requests."""
    total = 250

    def handler(request):
        offset = int(request.url.params["offset"])
        limit = int(request.url.params["limit"])
        batch = [{"id": i} for i in range(offset, min(offset + limit, total))]
        return httpx.Response(200, json={
            "data": batch,
            "pagination": {"totalCount": total},
        })

    patcher, requests = mock_http(handler)
    with patcher:
        matches = await HighlightlyClient().get_matches(season=2024)

    assert len(matches) == 250
    assert [int(r.url.params["offset"]) for r in requests] == [0, 100, 200]
    # No duplicates or gaps across page boundaries
    assert [m["id"] for m in matches] == list(range(250))


@pytest.mark.asyncio
async def test_highlightly_matches_exact_page_boundary():
    """Exactly 200 results should stop after 2 requests, not fire a 3rd
    empty request that burns part of the 100/day quota."""
    def handler(request):
        offset = int(request.url.params["offset"])
        return httpx.Response(200, json={
            "data": [{"id": i} for i in range(offset, offset + 100)],
            "pagination": {"totalCount": 200},
        })

    patcher, requests = mock_http(handler)
    with patcher:
        matches = await HighlightlyClient().get_matches(season=2024)

    assert len(matches) == 200
    assert len(requests) == 2


@pytest.mark.asyncio
async def test_highlightly_matches_stops_on_empty_batch():
    """If the API reports a bigger total than it actually returns,
    the loop must still terminate instead of spinning forever."""
    def handler(request):
        offset = int(request.url.params["offset"])
        data = [{"id": 1}] if offset == 0 else []
        return httpx.Response(200, json={
            "data": data,
            "pagination": {"totalCount": 9999},
        })

    patcher, requests = mock_http(handler)
    with patcher:
        matches = await HighlightlyClient().get_matches(season=2024)

    assert len(matches) == 1
    assert len(requests) == 2


@pytest.mark.asyncio
async def test_highlightly_box_score_and_player_paths():
    patcher, requests = mock_http(lambda r: httpx.Response(200, json=[]))

    with patcher:
        client = HighlightlyClient()
        await client.get_box_score(match_id=5001)
        await client.get_player_details(player_id=42)
        await client.get_players(limit=10, offset=20)

    assert requests[0].url.path == "/box-score/5001"
    assert requests[1].url.path == "/players/42"
    assert requests[2].url.params["offset"] == "20"


@pytest.mark.asyncio
async def test_highlightly_rate_limit_propagates():
    patcher, _ = mock_http(lambda r: httpx.Response(429))

    with patcher, pytest.raises(httpx.HTTPStatusError) as exc:
        await HighlightlyClient().get_box_score(match_id=1)

    assert exc.value.response.status_code == 429