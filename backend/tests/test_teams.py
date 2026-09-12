import pytest

from app.models.team import Team


@pytest.mark.asyncio
async def test_get_teams_empty(client, db_session):
    """Teams endpoint should return empty list when no teams exist."""
    response = await client.get("/teams")

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 0
    assert data["data"] == []
    assert data["limit"] == 25
    assert data["offset"] == 0


@pytest.mark.asyncio
async def test_get_teams_returns_data(client, db_session):
    """Teams endpoint should return teams that exist in the database."""
    team = Team(
        source="cfbd",
        external_id="646",
        league="cfb",
        name="Oklahoma State",
        abbreviation="OKST",
        conference="Big 12",
    )
    db_session.add(team)
    await db_session.commit()

    response = await client.get("/teams")

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["data"][0]["name"] == "Oklahoma State"
    assert data["data"][0]["conference"] == "Big 12"


@pytest.mark.asyncio
async def test_get_teams_filter_by_conference(client, db_session):
    """Conference filter should only return matching teams."""
    sec_team = Team(
        source="cfbd", external_id="1", league="cfb",
        name="Alabama", conference="SEC",
    )
    big12_team = Team(
        source="cfbd", external_id="2", league="cfb",
        name="Oklahoma State", conference="Big 12",
    )
    db_session.add_all([sec_team, big12_team])
    await db_session.commit()

    response = await client.get("/teams?conference=Big 12")

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["data"][0]["name"] == "Oklahoma State"


@pytest.mark.asyncio
async def test_get_teams_search(client, db_session):
    """Search should match partial team names case-insensitively."""
    team1 = Team(
        source="cfbd", external_id="1", league="cfb",
        name="Oklahoma State", conference="Big 12",
    )
    team2 = Team(
        source="cfbd", external_id="2", league="cfb",
        name="Texas", conference="Big 12",
    )
    db_session.add_all([team1, team2])
    await db_session.commit()

    response = await client.get("/teams?search=oklahoma")

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["data"][0]["name"] == "Oklahoma State"


@pytest.mark.asyncio
async def test_get_teams_pagination(client, db_session):
    """Pagination should limit results and report correct total."""
    for i in range(5):
        db_session.add(Team(
            source="cfbd", external_id=str(i), league="cfb",
            name=f"Team {i}",
        ))
    await db_session.commit()

    response = await client.get("/teams?limit=2&offset=0")

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 5
    assert len(data["data"]) == 2


@pytest.mark.asyncio
async def test_get_team_by_id(client, db_session):
    """Should return a single team by its ID."""
    team = Team(
        source="cfbd", external_id="646", league="cfb",
        name="Oklahoma State", abbreviation="OKST", conference="Big 12",
    )
    db_session.add(team)
    await db_session.commit()

    response = await client.get(f"/teams/{team.id}")

    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Oklahoma State"


@pytest.mark.asyncio
async def test_get_team_not_found(client):
    """Should return 404 for a team ID that doesn't exist."""
    response = await client.get("/teams/99999")
    assert response.status_code == 404