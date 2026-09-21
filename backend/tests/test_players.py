import pytest

from app.models.team import Team
from app.models.player import Player


async def _seed_players(db_session):
    """Two teams, three players across two leagues and positions."""
    eagles = Team(source="highlightly", external_id="1", league="nfl", name="Philadelphia Eagles")
    cowboys = Team(source="highlightly", external_id="2", league="nfl", name="Dallas Cowboys")
    db_session.add_all([eagles, cowboys])
    await db_session.commit()

    hurts = Player(
        source="highlightly", external_id="10", league="nfl", team_id=eagles.id,
        first_name="Jalen", last_name="Hurts", position="QB", number=1,
    )
    barkley = Player(
        source="highlightly", external_id="11", league="nfl", team_id=eagles.id,
        first_name="Saquon", last_name="Barkley", position="RB", number=26,
    )
    gordon = Player(
        source="cfbd", external_id="99", league="cfb", team_id=None,
        first_name="Ollie", last_name="Gordon", position="RB", number=0,
    )
    db_session.add_all([hurts, barkley, gordon])
    await db_session.commit()
    return eagles, cowboys, hurts, barkley, gordon


@pytest.mark.asyncio
async def test_get_players_empty(client):
    """Players endpoint should return an empty page when no players exist."""
    response = await client.get("/players")

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 0
    assert data["data"] == []


@pytest.mark.asyncio
async def test_get_players_resolves_team_name(client, db_session):
    """Each player should come back with their team name, or None if unassigned."""
    await _seed_players(db_session)

    response = await client.get("/players")

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 3
    by_last = {p["last_name"]: p for p in data["data"]}
    assert by_last["Hurts"]["team_name"] == "Philadelphia Eagles"
    assert by_last["Gordon"]["team_name"] is None


@pytest.mark.asyncio
async def test_get_players_ordered_by_last_name(client, db_session):
    """Results should be sorted alphabetically by last name."""
    await _seed_players(db_session)

    response = await client.get("/players")

    names = [p["last_name"] for p in response.json()["data"]]
    assert names == ["Barkley", "Gordon", "Hurts"]


@pytest.mark.asyncio
async def test_get_players_filter_by_team(client, db_session):
    eagles, _, _, _, _ = await _seed_players(db_session)

    response = await client.get(f"/players?team_id={eagles.id}")

    data = response.json()
    assert data["total"] == 2
    assert {p["last_name"] for p in data["data"]} == {"Hurts", "Barkley"}


@pytest.mark.asyncio
async def test_get_players_filter_by_position(client, db_session):
    await _seed_players(db_session)

    response = await client.get("/players?position=RB")

    data = response.json()
    assert data["total"] == 2
    assert all(p["position"] == "RB" for p in data["data"])


@pytest.mark.asyncio
async def test_get_players_filter_by_league(client, db_session):
    await _seed_players(db_session)

    response = await client.get("/players?league=cfb")

    data = response.json()
    assert data["total"] == 1
    assert data["data"][0]["last_name"] == "Gordon"


@pytest.mark.asyncio
async def test_get_players_filters_combine(client, db_session):
    """Multiple filters should AND together, not OR."""
    await _seed_players(db_session)

    response = await client.get("/players?position=RB&league=nfl")

    data = response.json()
    assert data["total"] == 1
    assert data["data"][0]["last_name"] == "Barkley"


@pytest.mark.asyncio
async def test_get_players_search_matches_first_or_last_name(client, db_session):
    """Search should hit first name or last name, case-insensitively."""
    await _seed_players(db_session)

    by_first = await client.get("/players?search=jalen")
    by_last = await client.get("/players?search=BARK")

    assert by_first.json()["data"][0]["last_name"] == "Hurts"
    assert by_last.json()["data"][0]["last_name"] == "Barkley"


@pytest.mark.asyncio
async def test_get_players_pagination(client, db_session):
    await _seed_players(db_session)

    response = await client.get("/players?limit=2&offset=2")

    data = response.json()
    assert data["total"] == 3
    assert len(data["data"]) == 1
    assert data["data"][0]["last_name"] == "Hurts"


@pytest.mark.asyncio
async def test_get_players_limit_over_max_rejected(client):
    """limit is capped at 100 by the Query validator."""
    response = await client.get("/players?limit=500")
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_get_player_by_id(client, db_session):
    _, _, hurts, _, _ = await _seed_players(db_session)

    response = await client.get(f"/players/{hurts.id}")

    assert response.status_code == 200
    data = response.json()
    assert data["first_name"] == "Jalen"
    assert data["team_name"] == "Philadelphia Eagles"


@pytest.mark.asyncio
async def test_get_player_not_found(client):
    response = await client.get("/players/99999")
    assert response.status_code == 404