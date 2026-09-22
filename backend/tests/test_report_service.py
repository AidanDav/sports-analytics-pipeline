"""Tests for ReportService and the /reports routes.

anthropic.Anthropic is patched where report_service imports it, so
the service gets a MagicMock client. Tests control what "Claude"
returns and inspect exactly what prompt was sent, without an API key
or any token spend.
"""
from datetime import date
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import select

from app.models.game import Game
from app.models.player import Player
from app.models.player_stats import PlayerStats
from app.models.report import Report
from app.models.team import Team
from app.services.report_service import MODEL, ReportService

FAKE_REPORT = "## Week Overview\nThe Eagles beat the Cowboys 34-29."


@pytest.fixture()
def mock_claude():
    """Patch the Anthropic client and return the mock for assertions."""
    with patch("app.services.report_service.anthropic.Anthropic") as mock_cls:
        client = mock_cls.return_value
        client.messages.create.return_value = MagicMock(
            content=[MagicMock(text=FAKE_REPORT)]
        )
        yield client


async def _seed_week(db_session):
    """Week 1 NFL: one final game with passing/rushing/receiving leaders,
    one scheduled game, plus a CFB game in the same week that must not
    leak into an NFL report."""
    phi = Team(source="highlightly", external_id="1", league="nfl", name="Philadelphia Eagles")
    dal = Team(source="highlightly", external_id="2", league="nfl", name="Dallas Cowboys")
    okst = Team(source="cfbd", external_id="197", league="cfb", name="Oklahoma State")
    db_session.add_all([phi, dal, okst])
    await db_session.commit()

    final = Game(
        source="highlightly", external_id="5001", league="nfl", season=2024, week=1,
        home_team_id=phi.id, away_team_id=dal.id, home_score=34, away_score=29,
        status="final", game_date=date(2024, 9, 6), venue="Lincoln Financial Field",
    )
    scheduled = Game(
        source="highlightly", external_id="5002", league="nfl", season=2024, week=1,
        home_team_id=dal.id, away_team_id=phi.id, status="scheduled",
    )
    college = Game(
        source="cfbd", external_id="401", league="cfb", season=2024, week=1,
        home_team_id=okst.id, home_score=52, away_score=0, status="final",
    )
    db_session.add_all([final, scheduled, college])
    await db_session.commit()

    hurts = Player(source="highlightly", external_id="101", league="nfl",
                   first_name="Jalen", last_name="Hurts")
    barkley = Player(source="highlightly", external_id="102", league="nfl",
                     first_name="Saquon", last_name="Barkley")
    lamb = Player(source="highlightly", external_id="201", league="nfl",
                  first_name="CeeDee", last_name="Lamb")
    db_session.add_all([hurts, barkley, lamb])
    await db_session.commit()

    db_session.add_all([
        PlayerStats(source="highlightly", player_id=hurts.id, game_id=final.id,
                    stat_category="passing", attempts=34, completions=23,
                    yards=278.0, touchdowns=2),
        PlayerStats(source="highlightly", player_id=barkley.id, game_id=final.id,
                    stat_category="rushing", carries=24, yards=109.0, touchdowns=2),
        PlayerStats(source="highlightly", player_id=lamb.id, game_id=final.id,
                    stat_category="receiving", receptions=5, yards=91.0, touchdowns=0),
    ])
    await db_session.commit()


def _sent_prompt(mock_claude) -> str:
    """Pull the user prompt out of the mocked messages.create call."""
    kwargs = mock_claude.messages.create.call_args.kwargs
    return kwargs["messages"][0]["content"]


# --- Service ---

@pytest.mark.asyncio
async def test_generate_report_success(db_session, mock_claude):
    await _seed_week(db_session)
    service = ReportService(db_session)

    report = await service.generate_weekly_report(season=2024, week=1, league="nfl")

    assert report.status == "complete"
    assert report.content == FAKE_REPORT
    assert report.title == "2024 NFL Season - Week 1 Summary"
    assert report.model == MODEL
    mock_claude.messages.create.assert_called_once()


@pytest.mark.asyncio
async def test_generate_report_prompt_contains_real_data(db_session, mock_claude):
    """The prompt is the contract with Claude. Verify the numbers in it
    come from the database so the 'do not invent stats' instruction
    has something real to anchor to."""
    await _seed_week(db_session)
    service = ReportService(db_session)

    report = await service.generate_weekly_report(season=2024, week=1)
    prompt = _sent_prompt(mock_claude)

    assert "Dallas Cowboys 29 at Philadelphia Eagles 34" in prompt
    assert "Lincoln Financial Field" in prompt
    assert "Jalen Hurts: 278.0 yards, 23/34, 2 TD" in prompt
    assert "Saquon Barkley: 109.0 yards, 24 carries" in prompt
    assert "CeeDee Lamb: 91.0 yards, 5 rec" in prompt
    # Stored for debugging and prompt iteration
    assert report.prompt_used == prompt


@pytest.mark.asyncio
async def test_generate_report_excludes_other_league_and_unplayed(db_session, mock_claude):
    """CFB games in the same week and unfinished NFL games stay out."""
    await _seed_week(db_session)
    service = ReportService(db_session)

    await service.generate_weekly_report(season=2024, week=1, league="nfl")
    prompt = _sent_prompt(mock_claude)

    assert "Oklahoma State" not in prompt
    assert prompt.count(" at ") == 1  # only the one final NFL game


@pytest.mark.asyncio
async def test_generate_report_uses_model_and_token_cap(db_session, mock_claude):
    await _seed_week(db_session)
    service = ReportService(db_session)

    await service.generate_weekly_report(season=2024, week=1)

    kwargs = mock_claude.messages.create.call_args.kwargs
    assert kwargs["model"] == MODEL
    assert kwargs["max_tokens"] == 2000


@pytest.mark.asyncio
async def test_generate_report_no_games_skips_claude(db_session, mock_claude):
    """No completed games means no API call, so no wasted tokens."""
    service = ReportService(db_session)

    report = await service.generate_weekly_report(season=2024, week=18)

    assert report.status == "failed"
    assert "No completed games" in report.content
    mock_claude.messages.create.assert_not_called()


@pytest.mark.asyncio
async def test_generate_report_claude_error_marks_failed(db_session, mock_claude):
    """An API error (rate limit, overload, bad key) is recorded, not raised."""
    await _seed_week(db_session)
    mock_claude.messages.create.side_effect = Exception("529 overloaded_error")
    service = ReportService(db_session)

    report = await service.generate_weekly_report(season=2024, week=1)

    assert report.status == "failed"
    assert "overloaded" in report.content


@pytest.mark.asyncio
async def test_generate_report_persists_row(db_session, mock_claude):
    await _seed_week(db_session)
    service = ReportService(db_session)

    await service.generate_weekly_report(season=2024, week=1)
    await db_session.commit()

    rows = (await db_session.execute(select(Report))).scalars().all()
    assert len(rows) == 1
    assert rows[0].season == 2024
    assert rows[0].week == 1


# --- Routes ---

@pytest.mark.asyncio
async def test_generate_report_endpoint(client, db_session, mock_claude):
    await _seed_week(db_session)

    response = await client.post("/reports/generate/weekly?season=2024&week=1&league=nfl")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "complete"
    assert data["content"] == FAKE_REPORT


@pytest.mark.asyncio
async def test_list_reports_filters(client, db_session):
    db_session.add_all([
        Report(report_type="weekly_summary", title="W1", content="a", prompt_used="",
               model=MODEL, status="complete", season=2024, week=1),
        Report(report_type="weekly_summary", title="W1 2023", content="b", prompt_used="",
               model=MODEL, status="complete", season=2023, week=1),
    ])
    await db_session.commit()

    response = await client.get("/reports?season=2024")

    data = response.json()
    assert data["total"] == 1
    assert data["data"][0]["title"] == "W1"


@pytest.mark.asyncio
async def test_get_report_by_id_and_404(client, db_session):
    report = Report(report_type="weekly_summary", title="W1", content="x",
                    prompt_used="", model=MODEL, status="complete")
    db_session.add(report)
    await db_session.commit()

    found = await client.get(f"/reports/{report.id}")
    missing = await client.get("/reports/99999")

    assert found.status_code == 200
    assert found.json()["title"] == "W1"
    assert missing.status_code == 404

# --- Conference-scoped reports ---

async def _seed_cfb_week(db_session):
    """2024 CFB Week 5: one final SEC game, one final Big Ten game."""
    bama = Team(source="cfbd", external_id="c1", league="cfb", name="Alabama", conference="SEC")
    uga = Team(source="cfbd", external_id="c2", league="cfb", name="Georgia", conference="SEC")
    osu = Team(source="cfbd", external_id="c3", league="cfb", name="Ohio State", conference="Big Ten")
    msu = Team(source="cfbd", external_id="c4", league="cfb", name="Michigan State", conference="Big Ten")
    db_session.add_all([bama, uga, osu, msu])
    await db_session.commit()

    db_session.add_all([
        Game(source="cfbd", external_id="c100", league="cfb", season=2024, week=5,
             home_team_id=bama.id, away_team_id=uga.id,
             home_score=41, away_score=34, status="final",
             venue="Bryant-Denny Stadium"),
        Game(source="cfbd", external_id="c101", league="cfb", season=2024, week=5,
             home_team_id=osu.id, away_team_id=msu.id,
             home_score=38, away_score=7, status="final",
             venue="Ohio Stadium"),
    ])
    await db_session.commit()


@pytest.mark.asyncio
async def test_conference_report_scopes_games_and_title(db_session, mock_claude):
    await _seed_cfb_week(db_session)
    service = ReportService(db_session)

    report = await service.generate_weekly_report(
        season=2024, week=5, league="cfb", conference="SEC"
    )
    prompt = _sent_prompt(mock_claude)

    assert report.status == "complete"
    assert report.title == "2024 SEC - Week 5 Summary"
    # Scope label and selection rule both reach Claude
    assert "2024 SEC College Football Season, Week 5" in prompt
    assert "games involving SEC teams" in prompt
    # Only the SEC game is in the data
    assert "Georgia 34 at Alabama 41" in prompt
    assert "Ohio State" not in prompt


@pytest.mark.asyncio
async def test_unscoped_cfb_report_has_no_conference_note(db_session, mock_claude):
    """Without a conference, the prompt and title keep the original format."""
    await _seed_cfb_week(db_session)
    service = ReportService(db_session)

    report = await service.generate_weekly_report(season=2024, week=5, league="cfb")
    prompt = _sent_prompt(mock_claude)

    assert report.title == "2024 College Football Season - Week 5 Summary"
    assert "games involving" not in prompt
    assert "Alabama" in prompt and "Ohio State" in prompt


@pytest.mark.asyncio
async def test_conference_with_no_games_skips_claude(db_session, mock_claude):
    """A valid conference with no games that week fails without spending tokens."""
    await _seed_cfb_week(db_session)
    service = ReportService(db_session)

    report = await service.generate_weekly_report(
        season=2024, week=5, league="cfb", conference="ACC"
    )

    assert report.status == "failed"
    mock_claude.messages.create.assert_not_called()


@pytest.mark.asyncio
async def test_generate_endpoint_passes_conference(client, db_session, mock_claude):
    await _seed_cfb_week(db_session)

    response = await client.post(
        "/reports/generate/weekly",
        params={"season": 2024, "week": 5, "league": "cfb", "conference": "Power 4"},
    )

    assert response.status_code == 200
    assert response.json()["title"] == "2024 Power 4 - Week 5 Summary"
    prompt = _sent_prompt(mock_claude)
    # Preset expands, so both conferences' games are included
    assert "Alabama" in prompt and "Ohio State" in prompt


@pytest.mark.asyncio
@pytest.mark.parametrize("league, conference, detail", [
    ("nfl", "SEC", "only supported for league=cfb"),
    ("cfb", "Big 10", "Unknown conference"),
])
async def test_generate_endpoint_rejects_bad_conference(
    client, db_session, mock_claude, league, conference, detail
):
    """Bad input gets a 400 before any Report row is created or tokens spent."""
    response = await client.post(
        "/reports/generate/weekly",
        params={"season": 2024, "week": 5, "league": league, "conference": conference},
    )

    assert response.status_code == 400
    assert detail in response.json()["detail"]
    mock_claude.messages.create.assert_not_called()
    rows = (await db_session.execute(select(Report))).scalars().all()
    assert rows == []