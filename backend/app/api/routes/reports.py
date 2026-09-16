import logging

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.report import Report
from app.schemas import ReportResponse, PaginatedResponse
from app.services.report_service import ReportService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/reports", tags=["reports"])


@router.post("/generate/weekly", response_model=ReportResponse)
async def generate_weekly_report(
    season: int = 2024,
    week: int = 1,
    league: str = "nfl",
    db: AsyncSession = Depends(get_db),
):
    """Generate a weekly analytical report using Claude."""
    service = ReportService(db)
    report = await service.generate_weekly_report(
        season=season, week=week, league=league
    )
    return ReportResponse.model_validate(report)


@router.get("", response_model=PaginatedResponse[ReportResponse])
async def get_reports(
    report_type: str | None = None,
    season: int | None = None,
    limit: int = Query(default=25, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """List generated reports with optional filtering."""
    query = select(Report)

    if report_type:
        query = query.where(Report.report_type == report_type)
    if season:
        query = query.where(Report.season == season)

    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar()

    query = query.order_by(Report.created_at.desc()).offset(offset).limit(limit)
    result = await db.execute(query)
    reports = result.scalars().all()

    return PaginatedResponse(
        total=total,
        limit=limit,
        offset=offset,
        data=[ReportResponse.model_validate(r) for r in reports],
    )


@router.get("/{report_id}", response_model=ReportResponse)
async def get_report(report_id: int, db: AsyncSession = Depends(get_db)):
    """Get a single report by ID."""
    result = await db.execute(select(Report).where(Report.id == report_id))
    report = result.scalar_one_or_none()

    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    return ReportResponse.model_validate(report)