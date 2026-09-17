import logging

from fastapi import APIRouter
from pydantic import BaseModel

from app.core.scheduler import scheduler

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/scheduler", tags=["scheduler"])


class JobStatus(BaseModel):
    """Response model for a single scheduled job."""
    id: str
    name: str
    next_run: str | None
    trigger: str


class SchedulerStatus(BaseModel):
    """Response model for the full scheduler state."""
    running: bool
    job_count: int
    jobs: list[JobStatus]


@router.get("/status", response_model=SchedulerStatus)
async def get_scheduler_status():
    """Check which jobs are registered and when they fire next.

    This is the equivalent of `crontab -l` for our ingestion pipeline.
    Useful for debugging whether the scheduler is actually running
    and confirming job schedules are correct after deployment.
    """
    jobs = scheduler.get_jobs()

    return SchedulerStatus(
        running=scheduler.running,
        job_count=len(jobs),
        jobs=[
            JobStatus(
                id=job.id,
                name=job.name,
                next_run=str(job.next_run_time) if job.next_run_time else None,
                trigger=str(job.trigger),
            )
            for job in jobs
        ],
    )