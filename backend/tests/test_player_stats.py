import pytest

from app.models.game import Game
from app.models.player import Player
from app.models.player_stats import PlayerStats


async def _seed_stats(db_session):
    """One QB with passing + rushing lines across two games, plus a second
    player whose stats should never leak into the first player's results."""
    game1 = Game(source="highlightly", external_id="1", league="nfl", season=2024, week=1)
    game2 = Game(source="highlightly", external_id="2", league="nfl", season=2024, week=2)
    qb = Player(source="highlightly", external_id="10", league="nfl", last_name="Hurts")
    other = Player(source="highlightly", external_id="11", league="nfl", last_name="Barkley")
    db_session.add_all([game1, game2, qb, other])
    await db_session.commit()

    db_session.add_all([
        PlayerStats(source="highlightly", player_id=qb.id, game_id=game1.id,
                    stat_category="passing", attempts=30, completions=20,
                    yards=250.0, touchdowns=2, interceptions=0),
        PlayerStats(source="highlightly", player_id=qb.id, game_id=game1.id,
                    stat_category="rushing", carries=8, yards=40.0, touchdowns=1),
        PlayerStats(source="highlightly", player_id=qb.id, game_id=game2.id,
                    stat_category="passing", attempts=25, completions=18,
                    yards=210.0, touchdowns=1, interceptions=1),
        PlayerStats(source="highlightly", player_id=other.id, game_id=game1.id,
                    stat_category="rushing", carries=20, yards=120.0, touchdowns=2),
    ])
    await db_session.commit()
    return qb, other, game1, game2


@pytest.mark.asyncio
async def test_get_player_stats_empty(client):
    """A player with no stat lines returns an empty page, not a 404."""
    response = await client.get("/players/99999/stats")

    assert response.status_code == 200
    assert response.json()["total"] == 0


@pytest.mark.asyncio
async def test_get_player_stats_only_that_player(client, db_session):
    qb, _, _, _ = await _seed_stats(db_session)

    response = await client.get(f"/players/{qb.id}/stats")

    data = response.json()
    assert data["total"] == 3
    assert all(s["player_id"] == qb.id for s in data["data"])


@pytest.mark.asyncio
async def test_get_player_stats_filter_by_category(client, db_session):
    qb, _, _, _ = await _seed_stats(db_session)

    response = await client.get(f"/players/{qb.id}/stats?stat_category=passing")

    data = response.json()
    assert data["total"] == 2
    assert all(s["stat_category"] == "passing" for s in data["data"])


@pytest.mark.asyncio
async def test_get_player_stats_filter_by_game(client, db_session):
    qb, _, game1, _ = await _seed_stats(db_session)

    response = await client.get(f"/players/{qb.id}/stats?game_id={game1.id}")

    data = response.json()
    assert data["total"] == 2
    assert {s["stat_category"] for s in data["data"]} == {"passing", "rushing"}


@pytest.mark.asyncio
async def test_get_player_stats_newest_game_first(client, db_session):
    qb, _, _, game2 = await _seed_stats(db_session)

    response = await client.get(f"/players/{qb.id}/stats")

    assert response.json()["data"][0]["game_id"] == game2.id


@pytest.mark.asyncio
async def test_get_player_stats_fields_serialized(client, db_session):
    """Unused columns for a category should come back as null, not 0."""
    qb, _, game1, _ = await _seed_stats(db_session)

    response = await client.get(
        f"/players/{qb.id}/stats?game_id={game1.id}&stat_category=passing"
    )

    line = response.json()["data"][0]
    assert line["yards"] == 250.0
    assert line["completions"] == 20
    assert line["receptions"] is None
    assert line["carries"] is None