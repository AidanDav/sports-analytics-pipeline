"""Tests for the APScheduler setup in app.core.scheduler.

The scheduler is never started here. Two things are tested:
1. configure_scheduler registers the right jobs on the right schedules.
2. Each job wrapper calls its service correctly and commits on success,
   rolls back on failure. The DB session and services are mocked, so
   the wrappers run synchronously without waiting for a cron trigger.
"""
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core import scheduler as sched_module
from app.core.scheduler import configure_scheduler, scheduler


@pytest.fixture()
def registered_jobs():
    configure_scheduler()
    yield {job.id: job for job in scheduler.get_jobs()}
    # Leave the module-level scheduler clean for other tests
    scheduler.remove_all_jobs()
    scheduler.remove_listener(sched_module._job_listener)


@pytest.fixture()
def fake_session():
    """Replace async_session() with a context manager yielding a mock."""
    session = AsyncMock()
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=session)
    cm.__aexit__ = AsyncMock(return_value=False)
    with patch.object(sched_module, "async_session", return_value=cm):
        yield session


def _fake_run(status="success"):
    return MagicMock(status=status, rows_created=1, rows_updated=0, rows_skipped=0)


# --- Registration ---

def test_all_jobs_registered(registered_jobs):
    assert set(registered_jobs) == {
        "cfbd_teams", "cfbd_games", "cfbd_players",
        "highlightly_teams", "highlightly_matches", "highlightly_box_scores",
    }


@pytest.mark.parametrize("job_id, expected_fields", [
    ("cfbd_teams", {"hour": "6", "minute": "0"}),
    ("cfbd_games", {"hour": "7,23", "minute": "0"}),
    ("cfbd_players", {"day_of_week": "mon", "hour": "8"}),
    ("highlightly_teams", {"hour": "6", "minute": "30"}),
    ("highlightly_matches", {"hour": "7,23", "minute": "30"}),
    ("highlightly_box_scores", {"hour": "9,15", "minute": "0"}),
])
def test_job_schedules(registered_jobs, job_id, expected_fields):
    trigger = registered_jobs[job_id].trigger
    fields = {f.name: str(f) for f in trigger.fields}
    for name, value in expected_fields.items():
        assert fields[name] == value


def test_every_job_has_misfire_grace(registered_jobs):
    """Without this, a job due while the container was down is silently skipped."""
    for job in registered_jobs.values():
        assert job.misfire_grace_time is not None
        assert job.misfire_grace_time >= 3600


# --- Job wrappers ---

@pytest.mark.asyncio
async def test_box_score_job_respects_rate_limit_cap(fake_session):
    """limit=10 per run x 2 runs/day is what keeps us under Highlightly's
    100 req/day free tier. If someone bumps it, this test should fail."""
    with patch.object(sched_module, "HighlightlyIngestionService") as svc_cls:
        svc_cls.return_value.ingest_box_scores = AsyncMock(return_value=_fake_run())
        await sched_module.run_highlightly_box_scores()

    svc_cls.return_value.ingest_box_scores.assert_awaited_once_with(limit=10)
    fake_session.commit.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("job, service_name, method, kwarg", [
    ("run_cfbd_games", "CFBDIngestionService", "ingest_games", "year"),
    ("run_cfbd_players", "CFBDIngestionService", "ingest_players", "year"),
    ("run_highlightly_matches", "HighlightlyIngestionService", "ingest_matches", "season"),
])
async def test_season_jobs_default_to_current_year(fake_session, job, service_name, method, kwarg):
    with patch.object(sched_module, service_name) as svc_cls:
        setattr(svc_cls.return_value, method, AsyncMock(return_value=_fake_run()))
        await getattr(sched_module, job)()

    call = getattr(svc_cls.return_value, method).call_args
    assert call.kwargs[kwarg] == datetime.now().year


@pytest.mark.asyncio
@pytest.mark.parametrize("job, service_name, method", [
    ("run_cfbd_teams", "CFBDIngestionService", "ingest_teams"),
    ("run_cfbd_games", "CFBDIngestionService", "ingest_games"),
    ("run_cfbd_players", "CFBDIngestionService", "ingest_players"),
    ("run_highlightly_teams", "HighlightlyIngestionService", "ingest_teams"),
    ("run_highlightly_matches", "HighlightlyIngestionService", "ingest_matches"),
    ("run_highlightly_box_scores", "HighlightlyIngestionService", "ingest_box_scores"),
])
async def test_job_commits_on_success(fake_session, job, service_name, method):
    with patch.object(sched_module, service_name) as svc_cls:
        setattr(svc_cls.return_value, method, AsyncMock(return_value=_fake_run()))
        await getattr(sched_module, job)()

    fake_session.commit.assert_awaited_once()
    fake_session.rollback.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("job, service_name, method", [
    ("run_cfbd_teams", "CFBDIngestionService", "ingest_teams"),
    ("run_cfbd_games", "CFBDIngestionService", "ingest_games"),
    ("run_cfbd_players", "CFBDIngestionService", "ingest_players"),
    ("run_highlightly_teams", "HighlightlyIngestionService", "ingest_teams"),
    ("run_highlightly_matches", "HighlightlyIngestionService", "ingest_matches"),
    ("run_highlightly_box_scores", "HighlightlyIngestionService", "ingest_box_scores"),
])
async def test_job_rolls_back_and_swallows_error(fake_session, job, service_name, method):
    """An unexpected crash must roll back and must not propagate, or it
    would bubble into APScheduler and could take down the event loop."""
    with patch.object(sched_module, service_name) as svc_cls:
        setattr(svc_cls.return_value, method, AsyncMock(side_effect=RuntimeError("db gone")))
        await getattr(sched_module, job)()  # should not raise

    fake_session.rollback.assert_awaited_once()
    fake_session.commit.assert_not_awaited()


def test_job_listener_logs_outcomes(caplog):
    ok = MagicMock(exception=None, job_id="cfbd_teams")
    bad = MagicMock(exception=RuntimeError("boom"), job_id="cfbd_games")

    with caplog.at_level("INFO"):
        sched_module._job_listener(ok)
        sched_module._job_listener(bad)

    assert "cfbd_teams completed successfully" in caplog.text
    assert "cfbd_games failed: boom" in caplog.text