import pytest
from datetime import date

from sqlalchemy import select

from app.models.team import Team
from app.models.game import Game
from app.models.player import Player
from app.models.player_stats import PlayerStats


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

async def _seed_box_score(db_session):
    """One NFL game. Two Eagles players (Hurts with two lines) and one Cowboy."""
    eagles = Team(source="highlightly", external_id="1", league="nfl", name="Philadelphia Eagles")
    cowboys = Team(source="highlightly", external_id="2", league="nfl", name="Dallas Cowboys")
    db_session.add_all([eagles, cowboys])
    await db_session.commit()

    game = Game(
        source="highlightly", external_id="500", league="nfl",
        season=2024, week=1, home_team_id=eagles.id, away_team_id=cowboys.id,
        home_score=34, away_score=6, status="final",
    )
    hurts = Player(source="highlightly", external_id="10", league="nfl", team_id=eagles.id,
                   first_name="Jalen", last_name="Hurts", position="QB")
    barkley = Player(source="highlightly", external_id="11", league="nfl", team_id=eagles.id,
                     first_name="Saquon", last_name="Barkley", position="RB")
    lamb = Player(source="highlightly", external_id="12", league="nfl", team_id=cowboys.id,
                  first_name="CeeDee", last_name="Lamb", position="WR")
    db_session.add_all([game, hurts, barkley, lamb])
    await db_session.commit()

    db_session.add_all([
        PlayerStats(source="highlightly", player_id=hurts.id, game_id=game.id,
                    team_id=eagles.id,
                    stat_category="rushing", carries=8, yards=40.0, touchdowns=1),
        PlayerStats(source="highlightly", player_id=barkley.id, game_id=game.id,
                    team_id=eagles.id,
                    stat_category="rushing", carries=20, yards=120.0, touchdowns=2),
        PlayerStats(source="highlightly", player_id=hurts.id, game_id=game.id,
                    team_id=eagles.id,
                    stat_category="passing", attempts=30, completions=20,
                    yards=250.0, touchdowns=2, interceptions=0),
        PlayerStats(source="highlightly", player_id=lamb.id, game_id=game.id,
                    team_id=cowboys.id,
                    stat_category="receiving", receptions=6, targets=9, yards=90.0),
    ])
    await db_session.commit()
    return eagles, cowboys, game


@pytest.mark.asyncio
async def test_get_games_includes_team_ids(client, db_session):
    eagles, cowboys, _ = await _seed_box_score(db_session)

    response = await client.get("/games")

    game = response.json()["data"][0]
    assert game["home_team_id"] == eagles.id
    assert game["away_team_id"] == cowboys.id


@pytest.mark.asyncio
async def test_get_game_stats_resolves_players(client, db_session):
    _, _, game = await _seed_box_score(db_session)

    response = await client.get(f"/games/{game.id}/stats")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 4
    names = {line["player_name"] for line in data}
    assert names == {"Jalen Hurts", "Saquon Barkley", "CeeDee Lamb"}


@pytest.mark.asyncio
async def test_get_game_stats_filters_by_team(client, db_session):
    eagles, _, game = await _seed_box_score(db_session)

    response = await client.get(f"/games/{game.id}/stats", params={"team_id": eagles.id})

    data = response.json()
    assert all(line["team_id"] == eagles.id for line in data)
    assert "CeeDee Lamb" not in {line["player_name"] for line in data}


@pytest.mark.asyncio
async def test_get_game_stats_ordered_by_category_then_yards(client, db_session):
    """Seeded out of order on purpose, so this proves the sort."""
    eagles, _, game = await _seed_box_score(db_session)

    response = await client.get(f"/games/{game.id}/stats", params={"team_id": eagles.id})

    order = [(l["player_name"], l["stat_category"]) for l in response.json()]
    assert order == [
        ("Jalen Hurts", "passing"),
        ("Saquon Barkley", "rushing"),
        ("Jalen Hurts", "rushing"),
    ]


@pytest.mark.asyncio
async def test_get_game_stats_no_box_score(client, db_session):
    """A real game with no stat lines (every CFB game) is an empty list, not a 404."""
    team = Team(source="cfbd", external_id="1", league="cfb", name="Oklahoma State")
    db_session.add(team)
    await db_session.commit()
    game = Game(source="cfbd", external_id="1", league="cfb", season=2024, week=1,
                home_team_id=team.id)
    db_session.add(game)
    await db_session.commit()

    response = await client.get(f"/games/{game.id}/stats")

    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_get_game_stats_game_not_found(client):
    response = await client.get("/games/99999/stats")
    assert response.status_code == 404

@pytest.mark.asyncio
async def test_get_game_stats_uses_team_at_game_time(client, db_session):
    """A player who has since moved teams keeps his old lines under his old team."""
    eagles, cowboys, game = await _seed_box_score(db_session)
    barkley = (await db_session.execute(
        select(Player).where(Player.last_name == "Barkley")
    )).scalar_one()
    barkley.team_id = cowboys.id
    await db_session.commit()

    eagles_lines = (await client.get(
        f"/games/{game.id}/stats", params={"team_id": eagles.id}
    )).json()

    assert "Saquon Barkley" in {l["player_name"] for l in eagles_lines}