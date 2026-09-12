import logging

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.ingestion.cfbd_service import CFBDIngestionService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ingestion", tags=["ingestion"])


@router.post("/cfbd/teams")
async def ingest_cfbd_teams(db: AsyncSession = Depends(get_db)):
    """Trigger CFBD team ingestion."""
    service = CFBDIngestionService(db)
    run = await service.ingest_teams()
    return {
        "status": run.status,
        "rows_created": run.rows_created,
        "rows_updated": run.rows_updated,
        "error": run.error_message,
    }


@router.post("/cfbd/games")
async def ingest_cfbd_games(year: int = 2024, db: AsyncSession = Depends(get_db)):
    """Trigger CFBD game ingestion for a given year."""
    service = CFBDIngestionService(db)
    run = await service.ingest_games(year=year)
    return {
        "status": run.status,
        "rows_created": run.rows_created,
        "rows_updated": run.rows_updated,
        "error": run.error_message,
    }