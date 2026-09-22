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

async def _seed_conference_games(db_session):
    """Five CFB games covering each conference case, plus one NFL game.

    1. SEC team at home vs G5         -> matches SEC via home side
    2. Big Ten team on the road at FCS -> matches Big Ten via away side
    3. Big 12 vs G5                   -> Power 4 only through one team
    4. G5 vs FCS                      -> FBS, but not Power 4
    5. FCS vs FCS                     -> matches nothing
    6. NFL game                       -> no conferences at all
    """
    def team(ext_id, name, conference=None, league="cfb", source="cfbd"):
        return Team(source=source, external_id=ext_id, league=league,
                    name=name, conference=conference)

    bama = team("1", "Alabama", "SEC")
    osu = team("2", "Ohio State", "Big Ten")
    okst = team("3", "Oklahoma State", "Big 12")
    tulane = team("4", "Tulane", "American Athletic")
    ndsu = team("5", "North Dakota State", "MVFC")
    montana = team("6", "Montana", "Big Sky")
    eagles = team("10", "Philadelphia Eagles", league="nfl", source="highlightly")
    cowboys = team("11", "Dallas Cowboys", league="nfl", source="highlightly")
    db_session.add_all([bama, osu, okst, tulane, ndsu, montana, eagles, cowboys])
    await db_session.commit()

    def game(ext_id, home, away, league="cfb", source="cfbd"):
        return Game(source=source, external_id=ext_id, league=league,
                    season=2024, week=1,
                    home_team_id=home.id, away_team_id=away.id)

    db_session.add_all([
        game("1", bama, tulane),
        game("2", ndsu, osu),
        game("3", okst, tulane),
        game("4", tulane, ndsu),
        game("5", montana, ndsu),
        game("6", eagles, cowboys, league="nfl", source="highlightly"),
    ])
    await db_session.commit()


def _matchups(response):
    """Set of (away, home) pairs, so assertions don't depend on sort order."""
    return {(g["away_team"], g["home_team"]) for g in response.json()["data"]}


@pytest.mark.asyncio
@pytest.mark.parametrize("league, expected_total", [
    ("cfb", 5),
    ("nfl", 1),
])
async def test_get_games_filter_by_league(client, db_session, league, expected_total):
    await _seed_conference_games(db_session)

    response = await client.get(f"/games?league={league}")

    assert response.status_code == 200
    assert response.json()["total"] == expected_total


@pytest.mark.asyncio
@pytest.mark.parametrize("conference, expected", [
    # Home side match
    ("SEC", {("Tulane", "Alabama")}),
    # Away side match, the case a home-only filter would miss
    ("Big Ten", {("Ohio State", "North Dakota State")}),
    # Preset expands to all four P4 conferences
    ("Power 4", {
        ("Tulane", "Alabama"),
        ("Ohio State", "North Dakota State"),
        ("Tulane", "Oklahoma State"),
    }),
    # FBS includes G5 vs FCS, excludes FCS vs FCS and the NFL game
    ("All FBS", {
        ("Tulane", "Alabama"),
        ("Ohio State", "North Dakota State"),
        ("Tulane", "Oklahoma State"),
        ("North Dakota State", "Tulane"),
    }),
])
async def test_get_games_filter_by_conference(client, db_session, conference, expected):
    await _seed_conference_games(db_session)

    response = await client.get("/games", params={"conference": conference, "limit": 100})

    assert response.status_code == 200
    assert _matchups(response) == expected
    # total comes from the same filtered query, so pagination stays correct
    assert response.json()["total"] == len(expected)


@pytest.mark.asyncio
async def test_get_games_unknown_conference_returns_nothing(client, db_session):
    """The games route doesn't validate conference names (the reports
    route does), so a typo just returns an empty list, not an error."""
    await _seed_conference_games(db_session)

    response = await client.get("/games", params={"conference": "Big 10"})

    assert response.status_code == 200
    assert response.json()["total"] == 0