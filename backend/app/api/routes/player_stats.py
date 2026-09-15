import logging

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.player_stats import PlayerStats
from app.schemas import PlayerStatsResponse, PaginatedResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/players", tags=["player-stats"])


@router.get("/{player_id}/stats", response_model=PaginatedResponse[PlayerStatsResponse])
async def get_player_stats(
    player_id: int,
    stat_category: str | None = None,
    game_id: int | None = None,
    limit: int = Query(default=25, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """Get stat lines for a specific player, optionally filtered by category or game."""
    query = select(PlayerStats).where(PlayerStats.player_id == player_id)

    if stat_category:
        query = query.where(PlayerStats.stat_category == stat_category)
    if game_id:
        query = query.where(PlayerStats.game_id == game_id)

    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar()

    query = query.order_by(PlayerStats.game_id.desc()).offset(offset).limit(limit)
    result = await db.execute(query)
    stats = result.scalars().all()

    return PaginatedResponse(
        total=total,
        limit=limit,
        offset=offset,
        data=[PlayerStatsResponse.model_validate(s) for s in stats],
    )