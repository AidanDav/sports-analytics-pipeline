"""Tests for CFBDIngestionService.

The HTTP client is replaced with AsyncMocks returning canned payloads
shaped like real CFBD responses. Everything downstream of the network
call (field mapping, upsert logic, IngestionRun bookkeeping) runs for
real against the test database. No test here ever touches the CFBD API.
"""
from datetime import date
from unittest.mock import AsyncMock

import httpx
import pytest
from sqlalchemy import select

from app.ingestion.cfbd_service import CFBDIngestionService
from app.models.game import Game
from app.models.player import Player
from app.models.team import Team


# --- Canned CFBD payloads (trimmed to the fields the service reads) ---

CFBD_TEAMS = [
    {"id": 197, "school": "Oklahoma State", "abbreviation": "OKST", "conference": "Big 12", "classification": "fbs"},
    {"id": 251, "school": "Texas", "abbreviation": "TEX", "conference": "SEC", "classification": "fbs"},
]

CFBD_GAMES = [
    {
        "id": 401628374, "season": 2024, "week": 1,
        "homeTeam": "Oklahoma State", "awayTeam": "Texas",
        "homeClassification": "fbs", "awayClassification": "fbs",
        "homePoints": 34, "awayPoints": 27, "completed": True,
        "startDate": "2024-08-31T23:00:00.000Z", "venue": "Boone Pickens Stadium",
    },
    {
        # Opponent not in our teams table, and game not played yet
        "id": 401628375, "season": 2024, "week": 2,
        "homeTeam": "Oklahoma State", "awayTeam": "Some FCS School",
        "homeClassification": "fbs", "awayClassification": "fcs",
        "homePoints": None, "awayPoints": None, "completed": False,
        "startDate": "2024-09-07T18:00:00.000Z", "venue": None,
    },
]

CFBD_ROSTER = [
    {"id": "4430807", "firstName": "Ollie", "lastName": "Gordon",
     "team": "Oklahoma State", "position": "RB", "jersey": 0},
    {"id": "4432001", "firstName": "Alan", "lastName": "Bowman",
     "team": "Oklahoma State", "position": "QB", "jersey": 7},
]


@pytest.fixture()
def service(db_session):
    """A CFBD service whose client methods are all mocks."""
    svc = CFBDIngestionService(db_session)
    svc.client.get_teams = AsyncMock(return_value=CFBD_TEAMS)
    svc.client.get_games = AsyncMock(return_value=CFBD_GAMES)
    svc.client.get_roster = AsyncMock(return_value=CFBD_ROSTER)
    return svc


async def _all(db_session, model):
    return (await db_session.execute(select(model))).scalars().all()


# --- Teams ---

@pytest.mark.asyncio
async def test_ingest_teams_creates_and_maps_fields(service, db_session):
    run = await service.ingest_teams()

    assert run.status == "success"
    assert run.rows_created == 2
    assert run.rows_updated == 0

    teams = {t.name: t for t in await _all(db_session, Team)}
    okst = teams["Oklahoma State"]
    # CFBD "school" -> name, int id -> string external_id, league hardcoded
    assert okst.external_id == "197"
    assert okst.abbreviation == "OKST"
    assert okst.conference == "Big 12"
    assert okst.classification == "fbs"
    assert okst.league == "cfb"
    assert okst.source == "cfbd"


@pytest.mark.asyncio
async def test_ingest_teams_is_idempotent(service, db_session):
    """Running twice should update, not duplicate."""
    await service.ingest_teams()
    run = await service.ingest_teams()

    assert run.rows_created == 0
    assert run.rows_updated == 2
    assert len(await _all(db_session, Team)) == 2


@pytest.mark.asyncio
async def test_ingest_teams_picks_up_changes(service, db_session):
    """Conference realignment should overwrite the stored value."""
    await service.ingest_teams()

    service.client.get_teams.return_value = [
        {**CFBD_TEAMS[0], "conference": "Pac-12"},
    ]
    await service.ingest_teams()

    team = (await db_session.execute(
        select(Team).where(Team.external_id == "197")
    )).scalar_one()
    assert team.conference == "Pac-12"


@pytest.mark.asyncio
async def test_ingest_teams_api_failure_marks_run_failed(service, db_session):
    """A network error should be caught and recorded, not raised."""
    service.client.get_teams.side_effect = httpx.ConnectError("connection refused")

    run = await service.ingest_teams()

    assert run.status == "failed"
    assert "connection refused" in run.error_message
    assert run.completed_at is not None
    assert await _all(db_session, Team) == []


# --- Games ---

@pytest.mark.asyncio
async def test_ingest_games_resolves_team_names_to_ids(service, db_session):
    await service.ingest_teams()
    run = await service.ingest_games(year=2024)

    assert run.status == "success"
    assert run.rows_created == 2

    teams = {t.name: t.id for t in await _all(db_session, Team)}
    game = (await db_session.execute(
        select(Game).where(Game.external_id == "401628374")
    )).scalar_one()

    assert game.home_team_id == teams["Oklahoma State"]
    assert game.away_team_id == teams["Texas"]
    assert game.home_score == 34
    assert game.away_score == 27


@pytest.mark.asyncio
async def test_ingest_games_normalizes_status_and_date(service, db_session):
    await service.ingest_teams()
    await service.ingest_games(year=2024)

    games = {g.external_id: g for g in await _all(db_session, Game)}
    played = games["401628374"]
    upcoming = games["401628375"]

    # completed boolean -> status string
    assert played.status == "final"
    assert upcoming.status == "scheduled"
    # ISO timestamp -> date
    assert played.game_date == date(2024, 8, 31)


@pytest.mark.asyncio
async def test_ingest_games_unknown_team_gets_null_id(service, db_session):
    """An opponent we don't track should not break ingestion."""
    await service.ingest_teams()
    await service.ingest_games(year=2024)

    game = (await db_session.execute(
        select(Game).where(Game.external_id == "401628375")
    )).scalar_one()
    assert game.home_team_id is not None
    assert game.away_team_id is None
    assert game.home_score is None


@pytest.mark.asyncio
async def test_ingest_games_updates_scores_on_rerun(service, db_session):
    """A scheduled game that finishes should flip to final with scores."""
    await service.ingest_teams()
    await service.ingest_games(year=2024)

    finished = {**CFBD_GAMES[1], "homePoints": 45, "awayPoints": 3, "completed": True}
    service.client.get_games.return_value = [finished]
    run = await service.ingest_games(year=2024)

    assert run.rows_updated == 1
    game = (await db_session.execute(
        select(Game).where(Game.external_id == "401628375")
    )).scalar_one()
    assert game.status == "final"
    assert game.home_score == 45


# --- Players ---

@pytest.mark.asyncio
async def test_ingest_players_one_call_per_classification(service, db_session):
    await service.ingest_teams()

    run = await service.ingest_players(year=2024)

    assert run.status == "success"
    assert service.client.get_roster.await_count == 2
    service.client.get_roster.assert_any_await(year=2024, classification="fbs")
    service.client.get_roster.assert_any_await(year=2024, classification="fcs")
    # The mock returns the same roster twice: created once, then updated
    assert run.rows_created == 2
    assert run.rows_updated == 2


@pytest.mark.asyncio
async def test_ingest_players_maps_fields(service, db_session):
    await service.ingest_teams()
    await service.ingest_players(year=2024)

    teams = {t.name: t.id for t in await _all(db_session, Team)}
    gordon = {p.last_name: p for p in await _all(db_session, Player)}["Gordon"]

    assert gordon.first_name == "Ollie"
    assert gordon.position == "RB"
    assert gordon.number == 0
    assert gordon.team_id == teams["Oklahoma State"]
    assert gordon.league == "cfb"


@pytest.mark.asyncio
async def test_ingest_players_skips_unmatched_team_name(service, db_session):
    """Real CFBD data has typos like "SacredHeart" for "Sacred Heart"."""
    await service.ingest_teams()
    service.client.get_roster.return_value = CFBD_ROSTER + [
        {"id": "999", "firstName": "Johnny", "lastName": "Hobgood",
         "team": "SacredHeart", "position": "QB", "jersey": 13},
    ]

    await service.ingest_players(year=2024)

    names = {p.last_name for p in await _all(db_session, Player)}
    assert "Hobgood" not in names
    assert "Gordon" in names


@pytest.mark.asyncio
async def test_ingest_players_null_fields_do_not_overwrite(service, db_session):
    await service.ingest_teams()
    await service.ingest_players(year=2024)

    service.client.get_roster.return_value = [
        {**CFBD_ROSTER[0], "position": None, "jersey": None},
    ]
    await service.ingest_players(year=2024)

    gordon = {p.last_name: p for p in await _all(db_session, Player)}["Gordon"]
    assert gordon.position == "RB"
    assert gordon.number == 0


@pytest.mark.asyncio
async def test_ingest_players_failed_classification_continues(service, db_session):
    await service.ingest_teams()

    async def roster_side_effect(year, classification):
        if classification == "fcs":
            raise httpx.HTTPStatusError(
                "500", request=httpx.Request("GET", "http://x"),
                response=httpx.Response(500),
            )
        return CFBD_ROSTER

    service.client.get_roster.side_effect = roster_side_effect
    run = await service.ingest_players(year=2024)

    assert run.status == "success"
    assert run.rows_skipped == 1
    assert run.rows_created == 2

@pytest.mark.asyncio
async def test_ingest_teams_keeps_only_fbs_and_fcs(service, db_session):
    service.client.get_teams.return_value = CFBD_TEAMS + [
        {"id": 1, "school": "Murray State", "classification": "fcs"},
        {"id": 2, "school": "Ferris State", "classification": "ii"},
    ]

    run = await service.ingest_teams()

    names = {t.name for t in await _all(db_session, Team)}
    assert "Murray State" in names
    assert "Ferris State" not in names
    assert run.rows_skipped == 1


@pytest.mark.asyncio
async def test_ingest_games_skips_non_division_one(service, db_session):
    await service.ingest_teams()
    service.client.get_games.return_value = [
        {**CFBD_GAMES[0], "id": 1, "awayTeam": "Ferris State", "awayClassification": "ii"},
    ]

    run = await service.ingest_games(year=2024)

    assert run.rows_created == 0
    assert run.rows_skipped == 1
    assert await _all(db_session, Game) == []

@pytest.mark.asyncio
async def test_ingest_teams_sets_classification_on_existing_teams(service, db_session):
    """Teams created before the column existed must get it on the next sync."""
    db_session.add(Team(source="cfbd", external_id="197", league="cfb", name="Oklahoma State"))
    await db_session.commit()

    run = await service.ingest_teams()

    assert run.rows_updated == 1
    okst = {t.name: t for t in await _all(db_session, Team)}["Oklahoma State"]
    assert okst.classification == "fbs"