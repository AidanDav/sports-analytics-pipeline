"""Tests for HighlightlyIngestionService.

Two layers:
1. Normalization helpers (_parse_score, _map_status, _split_name,
   _map_stats, _infer_position). These are pure functions, so they're
   tested directly with no database or mocks.
2. Full ingestion flows with the HTTP client mocked. Payloads mirror
   the real Highlightly response shapes, including the nested team
   objects, the "21 - 7" score string, and the verbose stat entries.
"""
from datetime import date
from unittest.mock import AsyncMock

import httpx
import pytest
from sqlalchemy import select

from app.ingestion.highlightly_service import HighlightlyIngestionService
from app.models.game import Game
from app.models.player import Player
from app.models.player_stats import PlayerStats
from app.models.team import Team


# --- Canned Highlightly payloads ---

HL_TEAMS = [
    {"id": 1, "name": "Eagles", "displayName": "Philadelphia Eagles", "abbreviation": "PHI"},
    {"id": 2, "name": "Cowboys", "displayName": "Dallas Cowboys", "abbreviation": "DAL"},
    # Highlightly lists the conferences as teams; these must be skipped
    {"id": 900, "name": "AFC", "displayName": "AFC", "abbreviation": "AFC"},
    {"id": 901, "name": "NFC", "displayName": "NFC", "abbreviation": "NFC"},
]

HL_MATCHES = [
    {
        "id": 5001, "season": 2024, "round": "regular-season",
        "date": "2024-09-06T00:15:00.000Z",
        "homeTeam": {"id": 1, "name": "Eagles"},
        "awayTeam": {"id": 2, "name": "Cowboys"},
        "state": {"description": "Finished", "score": {"current": "34 - 29"}},
    },
    {
        "id": 5002, "season": 2024, "round": "regular-season",
        "date": "2024-09-13T00:15:00.000Z",
        "homeTeam": {"id": 2, "name": "Cowboys"},
        "awayTeam": {"id": 1, "name": "Eagles"},
        # Real Highlightly shape: unplayed games report "0 - 0", not null
        "state": {"description": "Scheduled", "score": {"current": "0 - 0"}},
    },
]


def _stat(group, name, value):
    return {"group": group, "name": name, "value": value}


HL_BOX_SCORE = [
    {
        "team": {
            "id": 1,
            "boxScores": [
                {
                    "player": {"id": 101, "name": "Jalen Hurts", "jersey": 1},
                    "statistics": [
                        _stat("Passing", "Total Passes", 34),
                        _stat("Passing", "Total Successful Passes", 23),
                        _stat("Passing", "Total Passing Yards", 278),
                        _stat("Passing", "Total Passing Touchdowns", 2),
                        _stat("Passing", "Total Passing Interceptions", 1),
                        _stat("Rushing", "Total Rushing Attempts", 7),
                        _stat("Rushing", "Total Rushing Yards", 33),
                    ],
                },
                {
                    "player": {"id": 102, "name": "Saquon Barkley", "jersey": 26},
                    "statistics": [
                        _stat("Rushing", "Total Rushing Attempts", 24),
                        _stat("Rushing", "Total Rushing Yards", 109),
                        _stat("Rushing", "Total Rushing Touchdowns", 2),
                    ],
                },
            ],
        }
    },
    {
        "team": {
            "id": 2,
            "boxScores": [
                {
                    "player": {"id": 201, "name": "CeeDee Lamb", "jersey": 88},
                    "statistics": [
                        _stat("Receiving", "Total Receptions", 5),
                        _stat("Receiving", "Total Receiving Yards", 91),
                        _stat("Receiving", "Total Receiving Targets", 8),
                    ],
                },
            ],
        }
    },
]


@pytest.fixture()
def service(db_session):
    svc = HighlightlyIngestionService(db_session)
    svc.client.get_teams = AsyncMock(return_value=HL_TEAMS)
    svc.client.get_matches = AsyncMock(return_value=HL_MATCHES)
    svc.client.get_box_score = AsyncMock(return_value=HL_BOX_SCORE)
    return svc


@pytest.fixture()
def helpers():
    """Service instance for testing pure helpers. No DB needed."""
    return HighlightlyIngestionService(db=None)


async def _all(db_session, model):
    return (await db_session.execute(select(model))).scalars().all()


# =====================================================================
# Layer 1: normalization helpers
# =====================================================================

@pytest.mark.parametrize("raw, expected", [
    ("21 - 7", (21, 7)),
    ("0 - 0", (0, 0)),
    ("", (None, None)),
    (None, (None, None)),         # unplayed games can send a null score
    ("21-7", (None, None)),       # missing spaces around the dash
    ("TBD - TBD", (None, None)),
])
def test_parse_score(helpers, raw, expected):
    assert helpers._parse_score(raw) == expected


@pytest.mark.parametrize("raw, expected", [
    ("Finished", "final"),
    ("Scheduled", "scheduled"),
    ("In progress", "in_progress"),
    ("Half time", "in_progress"),
    ("Postponed", "postponed"),
    (None, "scheduled"),
    ("Some New Status", "scheduled"),  # unknown values fall back safely
])
def test_map_status(helpers, raw, expected):
    assert helpers._map_status(raw) == expected


@pytest.mark.parametrize("raw, expected", [
    ("Jalen Hurts", ("Jalen", "Hurts")),
    ("Patrick Surtain II", ("Patrick", "Surtain II")),
    ("Amon-Ra St. Brown", ("Amon-Ra", "St. Brown")),
    ("Cher", (None, "Cher")),
])
def test_split_name(helpers, raw, expected):
    assert helpers._split_name(raw) == expected


def test_map_stats_groups_by_category(helpers):
    stats = HL_BOX_SCORE[0]["team"]["boxScores"][0]["statistics"]

    result = helpers._map_stats(stats)

    assert set(result) == {"passing", "rushing"}
    assert result["passing"] == {
        "stat_category": "passing",
        "attempts": 34, "completions": 23, "yards": 278,
        "touchdowns": 2, "interceptions": 1,
    }
    # "yards" is reused across categories without colliding
    assert result["rushing"]["yards"] == 33
    assert result["rushing"]["carries"] == 7


def test_map_stats_ignores_unknown_and_null(helpers):
    stats = [
        _stat("Passing", "Total Passing Yards", 100),
        _stat("Passing", "Longest Pass", 55),        # not in our schema
        _stat("Passing", "Total Passing Touchdowns", None),
    ]

    result = helpers._map_stats(stats)

    assert result["passing"] == {"stat_category": "passing", "yards": 100}


@pytest.mark.parametrize("groups, expected", [
    (["Passing", "Rushing"], "QB"),
    (["Rushing"], "RB"),
    (["Rushing", "Receiving"], "WR"),
    (["Receiving"], "WR"),
    (["Defense"], "DEF"),
    (["Kicking"], "K"),
    ([], None),
])
def test_infer_position(helpers, groups, expected):
    stats = [{"group": g} for g in groups]
    assert helpers._infer_position(stats) == expected


# =====================================================================
# Layer 2: ingestion flows with mocked client
# =====================================================================

@pytest.mark.asyncio
async def test_ingest_teams_skips_conference_placeholders(service, db_session):
    run = await service.ingest_teams(league="NFL")

    assert run.status == "success"
    assert run.rows_created == 2
    assert run.rows_skipped == 2

    names = {t.name for t in await _all(db_session, Team)}
    assert names == {"Philadelphia Eagles", "Dallas Cowboys"}


@pytest.mark.asyncio
async def test_ingest_teams_normalizes_league_and_name(service, db_session):
    await service.ingest_teams(league="NFL")

    eagles = (await db_session.execute(
        select(Team).where(Team.external_id == "1")
    )).scalar_one()
    assert eagles.league == "nfl"           # uppercase -> lowercase
    assert eagles.name == "Philadelphia Eagles"  # displayName, not name
    assert eagles.conference is None


@pytest.mark.asyncio
async def test_ingest_matches_parses_nested_payload(service, db_session):
    await service.ingest_teams()
    run = await service.ingest_matches(season=2024)

    assert run.status == "success"
    assert run.rows_created == 2

    teams = {t.external_id: t.id for t in await _all(db_session, Team)}
    game = (await db_session.execute(
        select(Game).where(Game.external_id == "5001")
    )).scalar_one()

    assert game.home_team_id == teams["1"]
    assert game.away_team_id == teams["2"]
    assert (game.home_score, game.away_score) == (34, 29)
    assert game.status == "final"
    assert game.week == 1                      # derived from date
    assert game.game_date == date(2024, 9, 6)
    assert game.league == "nfl"


@pytest.mark.asyncio
async def test_ingest_matches_scheduled_game_has_no_score(service, db_session):
    await service.ingest_teams()
    await service.ingest_matches(season=2024)

    game = (await db_session.execute(
        select(Game).where(Game.external_id == "5002")
    )).scalar_one()
    assert game.status == "scheduled"
    assert game.home_score is None
    assert game.week == 2


@pytest.mark.asyncio
async def test_ingest_matches_null_state_does_not_fail_run(service, db_session):
    """Regression: a null score/state on one match used to raise inside
    _parse_score and fail the entire run, dropping every other match."""
    await service.ingest_teams()
    weird = {**HL_MATCHES[1], "id": 5003, "state": None}
    service.client.get_matches.return_value = [HL_MATCHES[0], weird]

    run = await service.ingest_matches(season=2024)

    assert run.status == "success"
    assert run.rows_created == 2


# --- Week derivation ---
# Real 2024 NFL calendar: Week 1 opened Thu Sep 5 (stored as Fri Sep 6 UTC),
# so the anchor is Wed Sep 4.

def _m(round_str, iso):
    return {"round": round_str, "date": iso}


def test_season_anchor_is_wednesday_before_opener(helpers):
    matches = [
        _m("preseason", "2024-08-09T23:00:00.000Z"),    # ignored
        _m("regular-season", "2024-09-06T00:20:00.000Z"),
        _m("regular-season", "2024-09-08T17:00:00.000Z"),
    ]
    assert helpers._season_anchor(matches) == date(2024, 9, 4)


def test_season_anchor_none_without_regular_season(helpers):
    assert helpers._season_anchor([_m("preseason", "2024-08-09T23:00:00.000Z")]) is None
    assert helpers._season_anchor([]) is None


@pytest.mark.parametrize("iso, expected_week", [
    ("2024-09-06T00:20:00.000Z", 1),   # Thu night opener, stored as Fri UTC
    ("2024-09-08T17:00:00.000Z", 1),   # Sunday
    ("2024-09-10T00:15:00.000Z", 1),   # Monday Night Football, stored as Tue UTC
    ("2024-09-12T00:15:00.000Z", 2),   # next Thursday night
    ("2024-12-25T18:00:00.000Z", 17),  # Christmas (Wed) was Week 17
    ("2025-01-05T18:00:00.000Z", 18),  # final Sunday
])
def test_week_number_nfl_edge_cases(helpers, iso, expected_week):
    anchor = date(2024, 9, 4)
    game_date = helpers._parse_date(iso)
    assert helpers._week_number("regular-season", game_date, anchor) == expected_week


def test_week_number_none_for_preseason_and_missing_data(helpers):
    anchor = date(2024, 9, 4)
    d = date(2024, 9, 8)
    assert helpers._week_number("preseason", d, anchor) is None
    assert helpers._week_number("regular-season", None, anchor) is None
    assert helpers._week_number("regular-season", d, None) is None
    # A date before the anchor shouldn't produce week 0 or negative
    assert helpers._week_number("regular-season", date(2024, 9, 1), anchor) is None


@pytest.mark.parametrize("raw, expected", [
    ("2026-10-23T00:15:00.000Z", date(2026, 10, 23)),
    (None, None),
    ("", None),
    ("not a date", None),
])
def test_parse_date(helpers, raw, expected):
    assert helpers._parse_date(raw) == expected


@pytest.mark.asyncio
async def test_ingest_matches_preseason_has_no_week(service, db_session):
    await service.ingest_teams()
    preseason = {**HL_MATCHES[0], "id": 4001, "round": "preseason",
                 "date": "2024-08-09T23:00:00.000Z"}
    service.client.get_matches.return_value = [preseason, *HL_MATCHES]

    await service.ingest_matches(season=2024)

    games = {g.external_id: g for g in await _all(db_session, Game)}
    assert games["4001"].week is None
    # Preseason must not become the anchor and shift regular-season weeks
    assert games["5001"].week == 1


@pytest.mark.asyncio
async def test_ingest_matches_final_zero_zero_is_kept(service, db_session):
    """Only unplayed games lose their score. A finished 0-0 is a real result."""
    await service.ingest_teams()
    shutout = {**HL_MATCHES[0], "state": {"description": "Finished",
                                         "score": {"current": "0 - 0"}}}
    service.client.get_matches.return_value = [shutout]

    await service.ingest_matches(season=2024)

    game = (await _all(db_session, Game))[0]
    assert (game.home_score, game.away_score) == (0, 0)


@pytest.mark.asyncio
async def test_ingest_matches_rerun_backfills_week_and_clears_fake_score(service, db_session):
    """Re-ingesting corrects rows written by the old code: null week, 0-0."""
    await service.ingest_teams()
    db_session.add(Game(
        source="highlightly", external_id="5002", league="nfl", season=2024,
        week=None, home_score=0, away_score=0, status="scheduled",
    ))
    await db_session.commit()

    run = await service.ingest_matches(season=2024)

    assert run.rows_updated == 1
    game = (await db_session.execute(
        select(Game).where(Game.external_id == "5002")
    )).scalar_one()
    assert game.week == 2
    assert game.home_score is None


@pytest.mark.asyncio
async def test_ingest_matches_api_failure_marks_run_failed(service, db_session):
    service.client.get_matches.side_effect = httpx.ReadTimeout("timed out")

    run = await service.ingest_matches(season=2024)

    assert run.status == "failed"
    assert "timed out" in run.error_message


@pytest.mark.asyncio
async def test_ingest_box_scores_only_pulls_final_games(service, db_session):
    """The scheduled match should never cost an API call."""
    await service.ingest_teams()
    await service.ingest_matches(season=2024)

    await service.ingest_box_scores()

    assert service.client.get_box_score.await_count == 1
    service.client.get_box_score.assert_awaited_with(match_id=5001)


@pytest.mark.asyncio
async def test_ingest_box_scores_creates_players_and_stats(service, db_session):
    await service.ingest_teams()
    await service.ingest_matches(season=2024)
    run = await service.ingest_box_scores()

    assert run.status == "success"
    players = {p.last_name: p for p in await _all(db_session, Player)}
    assert set(players) == {"Hurts", "Barkley", "Lamb"}

    # Position inferred from stat groups
    assert players["Hurts"].position == "QB"
    assert players["Barkley"].position == "RB"
    assert players["Lamb"].position == "WR"

    # Players attached to the right team
    teams = {t.external_id: t.id for t in await _all(db_session, Team)}
    assert players["Lamb"].team_id == teams["2"]

    # Hurts: passing + rushing, Barkley: rushing, Lamb: receiving
    stats = await _all(db_session, PlayerStats)
    assert len(stats) == 4
    # 3 players + 4 stat lines
    assert run.rows_created == 7

    # Each stat line records the team from the box score
    lamb_stat = next(s for s in stats if s.player_id == players["Lamb"].id)
    assert lamb_stat.team_id == teams["2"]


@pytest.mark.asyncio
async def test_ingest_box_scores_stat_values(service, db_session):
    await service.ingest_teams()
    await service.ingest_matches(season=2024)
    await service.ingest_box_scores()

    hurts = (await db_session.execute(
        select(Player).where(Player.last_name == "Hurts")
    )).scalar_one()
    passing = (await db_session.execute(
        select(PlayerStats).where(
            PlayerStats.player_id == hurts.id,
            PlayerStats.stat_category == "passing",
        )
    )).scalar_one()

    assert passing.completions == 23
    assert passing.attempts == 34
    assert passing.yards == 278
    assert passing.interceptions == 1


@pytest.mark.asyncio
async def test_ingest_box_scores_rerun_does_not_duplicate(service, db_session):
    """Regression test for the Day 5 duplicate stat row bug. A rerun now
    skips processed games entirely instead of re-fetching them."""
    await service.ingest_teams()
    await service.ingest_matches(season=2024)
    await service.ingest_box_scores()
    service.client.get_box_score.reset_mock()

    run = await service.ingest_box_scores()

    assert service.client.get_box_score.await_count == 0
    assert run.rows_created == 0
    assert len(await _all(db_session, Player)) == 3
    assert len(await _all(db_session, PlayerStats)) == 4


@pytest.mark.asyncio
async def test_ingest_box_scores_respects_limit(service, db_session):
    """limit is what keeps us under the 100 req/day free tier."""
    await service.ingest_teams()
    # Make both matches final so there are two candidates
    finished = [
        {**m, "state": {"description": "Finished", "score": {"current": "10 - 3"}}}
        for m in HL_MATCHES
    ]
    service.client.get_matches.return_value = finished
    await service.ingest_matches(season=2024)

    await service.ingest_box_scores(limit=1)

    assert service.client.get_box_score.await_count == 1

@pytest.mark.asyncio
async def test_ingest_box_scores_advances_past_processed_games(service, db_session):
    """Two limit=1 runs should hit two different games, not the same one twice."""
    await service.ingest_teams()
    finished = [
        {**m, "state": {"description": "Finished", "score": {"current": "10 - 3"}}}
        for m in HL_MATCHES
    ]
    service.client.get_matches.return_value = finished
    await service.ingest_matches(season=2024)

    await service.ingest_box_scores(limit=1)
    await service.ingest_box_scores(limit=1)

    fetched = [c.kwargs["match_id"] for c in service.client.get_box_score.await_args_list]
    assert len(fetched) == 2
    assert len(set(fetched)) == 2

@pytest.mark.asyncio
async def test_ingest_box_scores_skips_failed_match(service, db_session):
    await service.ingest_teams()
    await service.ingest_matches(season=2024)
    service.client.get_box_score.side_effect = httpx.HTTPStatusError(
        "429 Too Many Requests",
        request=httpx.Request("GET", "http://x"),
        response=httpx.Response(429),
    )

    run = await service.ingest_box_scores()

    assert run.status == "success"
    assert run.rows_skipped == 1
    assert await _all(db_session, Player) == []