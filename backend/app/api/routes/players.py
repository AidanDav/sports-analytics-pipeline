import logging

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.player import Player
from app.models.team import Team
from app.schemas import PlayerResponse, PaginatedResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/players", tags=["players"])


@router.get("", response_model=PaginatedResponse[PlayerResponse])
async def get_players(
    team_id: int | None = None,
    position: str | None = None,
    search: str | None = None,
    league: str | None = None,
    limit: int = Query(default=25, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """List players with optional filtering and pagination."""
    query = select(Player)

    if team_id:
        query = query.where(Player.team_id == team_id)
    if position:
        query = query.where(Player.position == position)
    if league:
        query = query.where(Player.league == league)
    if search:
        # Match against first or last name
        query = query.where(
            Player.first_name.ilike(f"%{search}%")
            | Player.last_name.ilike(f"%{search}%")
        )

    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar()

    query = query.order_by(Player.last_name, Player.first_name).offset(offset).limit(limit)
    result = await db.execute(query)
    players = result.scalars().all()

    # Batch-resolve team names, same pattern as games route
    team_ids = {p.team_id for p in players if p.team_id}
    team_lookup = {}
    if team_ids:
        team_result = await db.execute(
            select(Team).where(Team.id.in_(team_ids))
        )
        team_lookup = {t.id: t.name for t in team_result.scalars().all()}

    return PaginatedResponse(
        total=total,
        limit=limit,
        offset=offset,
        data=[
            PlayerResponse(
                id=p.id,
                first_name=p.first_name,
                last_name=p.last_name,
                position=p.position,
                number=p.number,
                team_id=p.team_id,
                team_name=team_lookup.get(p.team_id),
                league=p.league,
            )
            for p in players
        ],
    )


@router.get("/{player_id}", response_model=PlayerResponse)
async def get_player(player_id: int, db: AsyncSession = Depends(get_db)):
    """Get a single player by ID."""
    result = await db.execute(select(Player).where(Player.id == player_id))
    player = result.scalar_one_or_none()

    if not player:
        raise HTTPException(status_code=404, detail="Player not found")

    # Resolve team name
    team_name = None
    if player.team_id:
        team_result = await db.execute(
            select(Team.name).where(Team.id == player.team_id)
        )
        team_name = team_result.scalar_one_or_none()

    return PlayerResponse(
        id=player.id,
        first_name=player.first_name,
        last_name=player.last_name,
        position=player.position,
        number=player.number,
        team_id=player.team_id,
        team_name=team_name,
        league=player.league,
    )