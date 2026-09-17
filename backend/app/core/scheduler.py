import logging
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED

from app.db.session import async_session
from app.ingestion.cfbd_service import CFBDIngestionService
from app.ingestion.highlightly_service import HighlightlyIngestionService

logger = logging.getLogger(__name__)

# The scheduler instance. AsyncIOScheduler works with FastAPI's event loop
# instead of spinning up its own thread pool like BackgroundScheduler would.
scheduler = AsyncIOScheduler()


def _job_listener(event):
    """Log job outcomes so we can monitor the scheduler's health.

    APScheduler fires events after each job completes. We hook into
    those to log success or failure without cluttering the job functions.
    """
    if event.exception:
        logger.error(
            f"Scheduled job {event.job_id} failed: {event.exception}"
        )
    else:
        logger.info(f"Scheduled job {event.job_id} completed successfully")


# --- Job wrappers ---
# Each job runs outside of a FastAPI request, so there's no dependency
# injection. We create a standalone database session, run the ingestion,
# commit on success, and roll back on failure. This is the same pattern
# a Celery worker or any background task would use.


async def run_cfbd_teams():
    """Scheduled job: sync college football teams from CFBD."""
    async with async_session() as session:
        try:
            service = CFBDIngestionService(session)
            run = await service.ingest_teams()
            await session.commit()
            logger.info(
                f"CFBD teams sync: {run.status} "
                f"({run.rows_created} created, {run.rows_updated} updated)"
            )
        except Exception as e:
            await session.rollback()
            logger.error(f"CFBD teams scheduled job failed: {e}")


async def run_cfbd_games(year: int | None = None):
    """Scheduled job: sync college football games from CFBD.

    Defaults to the current year if no year is provided,
    so the scheduler always pulls the active season.
    """
    if year is None:
        year = datetime.now().year

    async with async_session() as session:
        try:
            service = CFBDIngestionService(session)
            run = await service.ingest_games(year=year)
            await session.commit()
            logger.info(
                f"CFBD games sync ({year}): {run.status} "
                f"({run.rows_created} created, {run.rows_updated} updated)"
            )
        except Exception as e:
            await session.rollback()
            logger.error(f"CFBD games scheduled job failed: {e}")


async def run_cfbd_players(year: int | None = None):
    """Scheduled job: sync college football rosters from CFBD.

    This is the heaviest CFBD job because it fetches one roster
    per team. Runs less frequently to be respectful of the API.
    """
    if year is None:
        year = datetime.now().year

    async with async_session() as session:
        try:
            service = CFBDIngestionService(session)
            run = await service.ingest_players(year=year)
            await session.commit()
            logger.info(
                f"CFBD players sync ({year}): {run.status} "
                f"({run.rows_created} created, {run.rows_updated} updated)"
            )
        except Exception as e:
            await session.rollback()
            logger.error(f"CFBD players scheduled job failed: {e}")


async def run_highlightly_teams():
    """Scheduled job: sync NFL teams from Highlightly."""
    async with async_session() as session:
        try:
            service = HighlightlyIngestionService(session)
            run = await service.ingest_teams(league="NFL")
            await session.commit()
            logger.info(
                f"Highlightly teams sync: {run.status} "
                f"({run.rows_created} created, {run.rows_updated} updated)"
            )
        except Exception as e:
            await session.rollback()
            logger.error(f"Highlightly teams scheduled job failed: {e}")


async def run_highlightly_matches(season: int | None = None):
    """Scheduled job: sync NFL matches from Highlightly."""
    if season is None:
        season = datetime.now().year

    async with async_session() as session:
        try:
            service = HighlightlyIngestionService(session)
            run = await service.ingest_matches(season=season, league="NFL")
            await session.commit()
            logger.info(
                f"Highlightly matches sync ({season}): {run.status} "
                f"({run.rows_created} created, {run.rows_updated} updated)"
            )
        except Exception as e:
            await session.rollback()
            logger.error(f"Highlightly matches scheduled job failed: {e}")


async def run_highlightly_box_scores():
    """Scheduled job: pull box scores for completed NFL matches.

    The limit parameter is the key to respecting Highlightly's
    100 req/day free tier. Each box score is one API call, so
    we cap at 10 per run. With the scheduler running this twice
    a day, that's 20 box scores/day, leaving budget for manual
    triggers and other endpoints.
    """
    async with async_session() as session:
        try:
            service = HighlightlyIngestionService(session)
            run = await service.ingest_box_scores(limit=10)
            await session.commit()
            logger.info(
                f"Highlightly box scores sync: {run.status} "
                f"({run.rows_created} created, {run.rows_skipped} skipped)"
            )
        except Exception as e:
            await session.rollback()
            logger.error(f"Highlightly box scores scheduled job failed: {e}")


def configure_scheduler():
    """Register all ingestion jobs with their schedules.

    Schedule philosophy:
    - Teams rarely change, so sync once a day
    - Games/matches update with scores throughout the week, sync twice daily
    - Box scores are the most API-expensive, spread across two daily runs
    - CFBD players (rosters) sync weekly since rosters don't change often
    - All jobs use misfire_grace_time so if the app was down when a job
      was supposed to fire, it runs immediately on startup instead of
      silently skipping
    """
    # Listen for job success/failure events
    scheduler.add_listener(_job_listener, EVENT_JOB_EXECUTED | EVENT_JOB_ERROR)

    # --- CFBD jobs (college football) ---

    # Teams: daily at 6:00 AM UTC
    scheduler.add_job(
        run_cfbd_teams,
        "cron",
        hour=6,
        minute=0,
        id="cfbd_teams",
        name="CFBD Team Sync",
        misfire_grace_time=3600,  # 1 hour grace period
    )

    # Games: twice daily at 7:00 AM and 11:00 PM UTC
    # Morning run catches overnight updates, evening run catches game results
    scheduler.add_job(
        run_cfbd_games,
        "cron",
        hour="7,23",
        minute=0,
        id="cfbd_games",
        name="CFBD Game Sync",
        misfire_grace_time=3600,
    )

    # Players/rosters: weekly on Mondays at 8:00 AM UTC
    # Rosters change slowly, no need to pound the API daily
    scheduler.add_job(
        run_cfbd_players,
        "cron",
        day_of_week="mon",
        hour=8,
        minute=0,
        id="cfbd_players",
        name="CFBD Player/Roster Sync",
        misfire_grace_time=7200,
    )

    # --- Highlightly jobs (NFL) ---

    # Teams: daily at 6:30 AM UTC (offset from CFBD to avoid overlap)
    scheduler.add_job(
        run_highlightly_teams,
        "cron",
        hour=6,
        minute=30,
        id="highlightly_teams",
        name="Highlightly Team Sync",
        misfire_grace_time=3600,
    )

    # Matches: twice daily at 7:30 AM and 11:30 PM UTC
    scheduler.add_job(
        run_highlightly_matches,
        "cron",
        hour="7,23",
        minute=30,
        id="highlightly_matches",
        name="Highlightly Match Sync",
        misfire_grace_time=3600,
    )

    # Box scores: twice daily at 9:00 AM and 3:00 PM UTC
    # 10 per run * 2 runs = 20 box score calls/day, well within 100 limit
    scheduler.add_job(
        run_highlightly_box_scores,
        "cron",
        hour="9,15",
        minute=0,
        id="highlightly_box_scores",
        name="Highlightly Box Score Sync",
        misfire_grace_time=3600,
    )

    logger.info(
        f"Scheduler configured with {len(scheduler.get_jobs())} jobs"
    )