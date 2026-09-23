import logging

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.game import Game
from app.models.team import Team
from app.models.player import Player
from app.models.player_stats import PlayerStats
from app.schemas import (
    GameResponse, 
    GameStatLineResponse, 
    PlayerStatsResponse, 
    PaginatedResponse,
    )
from app.services.conferences import game_in_conference

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/games", tags=["games"])


@router.get("", response_model=PaginatedResponse[GameResponse])
async def get_games(
    season: int | None = None,
    week: int | None = None,
    team_id: int | None = None,
    league: str | None = None,
    conference: str | None = None,
    limit: int = Query(default=25, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """List games with optional filtering and pagination."""
    query = select(Game)

    if season:
        query = query.where(Game.season == season)
    if week:
        query = query.where(Game.week == week)
    if league:
        query = query.where(Game.league == league)
    if team_id:
        # A team can be home or away, so check both
        query = query.where(
            (Game.home_team_id == team_id) | (Game.away_team_id == team_id)
        )
    if conference:
        # Any game involving a team from the conference (or preset).
        # Only CFB teams have conferences, so this naturally returns
        # no NFL games.
        query = query.where(game_in_conference(conference))

    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar()

    query = query.order_by(Game.season.desc(), Game.week, Game.game_date).offset(offset).limit(limit)
    result = await db.execute(query)
    games = result.scalars().all()

    # Collect all team IDs we need to look up so we can resolve
    # names in one query instead of per-game
    team_ids = set()
    for game in games:
        if game.home_team_id:
            team_ids.add(game.home_team_id)
        if game.away_team_id:
            team_ids.add(game.away_team_id)

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
            GameResponse(
                id=game.id,
                season=game.season,
                week=game.week,
                home_team_id=game.home_team_id,
                away_team_id=game.away_team_id,
                home_team=team_lookup.get(game.home_team_id, "Unknown"),
                away_team=team_lookup.get(game.away_team_id, "Unknown"),
                home_score=game.home_score,
                away_score=game.away_score,
                game_date=str(game.game_date) if game.game_date else None,
                status=game.status,
                venue=game.venue,
            )
            for game in games
        ],
    )

# Box score reading order: offense first, then everything else
CATEGORY_ORDER = {"passing": 0, "rushing": 1, "receiving": 2, "defense": 3}


@router.get("/{game_id}/stats", response_model=list[GameStatLineResponse])
async def get_game_stats(
    game_id: int,
    team_id: int | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Every stat line from one game, optionally limited to one team.

    Returns a plain list instead of a paginated one. A single game's
    box score is naturally bounded, and the drill-down wants it all
    at once.

    team_id filters on the player's current team, so a traded
    player's old lines follow him to his new team.
    """
    game = (
        await db.execute(select(Game).where(Game.id == game_id))
    ).scalar_one_or_none()
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

    # Inner join: a stat line with no player has nothing to display
    query = (
        select(PlayerStats, Player)
        .join(Player, PlayerStats.player_id == Player.id)
        .where(PlayerStats.game_id == game_id)
    )
    if team_id:
        query = query.where(Player.team_id == team_id)

    rows = (await db.execute(query)).all()

    lines = [
        GameStatLineResponse(
            **PlayerStatsResponse.model_validate(stat).model_dump(),
            player_name=f"{player.first_name or ''} {player.last_name}".strip(),
            position=player.position,
            team_id=player.team_id,
        )
        for stat, player in rows
    ]

    # Sorted in Python, since mapping categories to a custom order in SQL
    # would need a CASE expression for a list this small
    lines.sort(key=lambda l: (CATEGORY_ORDER.get(l.stat_category, 99), -(l.yards or 0)))
    return lines