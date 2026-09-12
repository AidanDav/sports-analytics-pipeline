import logging

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.team import Team

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/teams", tags=["teams"])


@router.get("")
async def get_teams(
    conference: str | None = None,
    search: str | None = None,
    limit: int = Query(default=25, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """List teams with optional filtering and pagination."""
    query = select(Team)

    # Apply filters only if provided
    if conference:
        query = query.where(Team.conference == conference)
    if search:
        # ilike is case-insensitive LIKE. The % wildcards match
        # anything before and after the search term.
        query = query.where(Team.name.ilike(f"%{search}%"))

    # Get total count before pagination so the frontend knows
    # how many pages there are
    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar()

    # Apply pagination and ordering
    query = query.order_by(Team.name).offset(offset).limit(limit)
    result = await db.execute(query)
    teams = result.scalars().all()

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "data": [
            {
                "id": team.id,
                "name": team.name,
                "abbreviation": team.abbreviation,
                "conference": team.conference,
                "league": team.league,
            }
            for team in teams
        ],
    }


@router.get("/{team_id}")
async def get_team(team_id: int, db: AsyncSession = Depends(get_db)):
    """Get a single team by ID."""
    result = await db.execute(select(Team).where(Team.id == team_id))
    team = result.scalar_one_or_none()

    if not team:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Team not found")

    return {
        "id": team.id,
        "name": team.name,
        "abbreviation": team.abbreviation,
        "conference": team.conference,
        "league": team.league,
        "source": team.source,
        "external_id": team.external_id,
    }