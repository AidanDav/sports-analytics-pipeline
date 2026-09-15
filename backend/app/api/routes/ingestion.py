import logging

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.ingestion.cfbd_service import CFBDIngestionService
from app.ingestion.highlightly_service import HighlightlyIngestionService
from app.schemas import IngestionRunResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ingestion", tags=["ingestion"])


@router.post("/cfbd/teams", response_model=IngestionRunResponse)
async def ingest_cfbd_teams(db: AsyncSession = Depends(get_db)):
    """Trigger CFBD team ingestion."""
    service = CFBDIngestionService(db)
    run = await service.ingest_teams()
    return IngestionRunResponse(
        status=run.status,
        rows_created=run.rows_created,
        rows_updated=run.rows_updated,
        error=run.error_message,
    )


@router.post("/cfbd/games", response_model=IngestionRunResponse)
async def ingest_cfbd_games(year: int = 2024, db: AsyncSession = Depends(get_db)):
    """Trigger CFBD game ingestion for a given year."""
    service = CFBDIngestionService(db)
    run = await service.ingest_games(year=year)
    return IngestionRunResponse(
        status=run.status,
        rows_created=run.rows_created,
        rows_updated=run.rows_updated,
        error=run.error_message,
    )


@router.post("/highlightly/teams", response_model=IngestionRunResponse)
async def ingest_highlightly_teams(
    league: str = "NFL", db: AsyncSession = Depends(get_db)
):
    """Trigger Highlightly team ingestion."""
    service = HighlightlyIngestionService(db)
    run = await service.ingest_teams(league=league)
    return IngestionRunResponse(
        status=run.status,
        rows_created=run.rows_created,
        rows_updated=run.rows_updated,
        error=run.error_message,
    )


@router.post("/highlightly/matches", response_model=IngestionRunResponse)
async def ingest_highlightly_matches(
    season: int = 2024, league: str = "NFL", db: AsyncSession = Depends(get_db)
):
    """Trigger Highlightly match ingestion for a given season."""
    service = HighlightlyIngestionService(db)
    run = await service.ingest_matches(season=season, league=league)
    return IngestionRunResponse(
        status=run.status,
        rows_created=run.rows_created,
        rows_updated=run.rows_updated,
        error=run.error_message,
    )