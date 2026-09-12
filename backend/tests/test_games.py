import pytest
from datetime import date

from app.models.team import Team
from app.models.game import Game


@pytest.mark.asyncio
async def test_get_games_empty(client):
    """Games endpoint should return empty list when no games exist."""
    response = await client.get("/games")

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 0
    assert data["data"] == []


@pytest.mark.asyncio
async def test_get_games_with_team_names(client, db_session):
    """Games should resolve team IDs to names in the response."""
    home = Team(
        source="cfbd", external_id="1", league="cfb",
        name="Oklahoma State",
    )
    away = Team(
        source="cfbd", external_id="2", league="cfb",
        name="Texas",
    )
    db_session.add_all([home, away])
    await db_session.commit()

    game = Game(
        source="cfbd", external_id="100", league="cfb",
        season=2024, week=1,
        home_team_id=home.id, away_team_id=away.id,
        home_score=34, away_score=27,
        game_date=date(2024, 8, 31),
        status="final", venue="Boone Pickens Stadium",
    )
    db_session.add(game)
    await db_session.commit()

    response = await client.get("/games")

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["data"][0]["home_team"] == "Oklahoma State"
    assert data["data"][0]["away_team"] == "Texas"
    assert data["data"][0]["home_score"] == 34


@pytest.mark.asyncio
async def test_get_games_filter_by_season(client, db_session):
    """Season filter should only return games from that season."""
    team = Team(source="cfbd", external_id="1", league="cfb", name="Team A")
    db_session.add(team)
    await db_session.commit()

    game_2024 = Game(
        source="cfbd", external_id="1", league="cfb",
        season=2024, week=1, home_team_id=team.id,
    )
    game_2023 = Game(
        source="cfbd", external_id="2", league="cfb",
        season=2023, week=1, home_team_id=team.id,
    )
    db_session.add_all([game_2024, game_2023])
    await db_session.commit()

    response = await client.get("/games?season=2024")

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["data"][0]["season"] == 2024


@pytest.mark.asyncio
async def test_get_games_filter_by_team(client, db_session):
    """Team filter should return games where team is home or away."""
    team_a = Team(source="cfbd", external_id="1", league="cfb", name="Team A")
    team_b = Team(source="cfbd", external_id="2", league="cfb", name="Team B")
    team_c = Team(source="cfbd", external_id="3", league="cfb", name="Team C")
    db_session.add_all([team_a, team_b, team_c])
    await db_session.commit()

    # Team A is home
    game1 = Game(
        source="cfbd", external_id="1", league="cfb",
        season=2024, week=1,
        home_team_id=team_a.id, away_team_id=team_b.id,
    )
    # Team A is away
    game2 = Game(
        source="cfbd", external_id="2", league="cfb",
        season=2024, week=2,
        home_team_id=team_c.id, away_team_id=team_a.id,
    )
    # Team A not involved
    game3 = Game(
        source="cfbd", external_id="3", league="cfb",
        season=2024, week=3,
        home_team_id=team_b.id, away_team_id=team_c.id,
    )
    db_session.add_all([game1, game2, game3])
    await db_session.commit()

    response = await client.get(f"/games?team_id={team_a.id}")

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2