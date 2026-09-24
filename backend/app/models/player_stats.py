from datetime import datetime

from sqlalchemy import String, Integer, Float, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PlayerStats(Base):
    __tablename__ = "player_stats"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    # Ties this stat line to a specific player and game
    player_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("players.id", ondelete="CASCADE")
    )
    game_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("games.id", ondelete="CASCADE")
    )
    team_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("teams.id", ondelete="SET NULL"), index=True
    )
    # What category of stats: "passing", "rushing", "receiving", "defense"
    stat_category: Mapped[str] = mapped_column(String(30), nullable=False)
    # Individual stat fields -- nullable because not every category
    # uses every field. A rusher has yards and touchdowns but no
    # completions. A passer has completions but no receptions.
    attempts: Mapped[int | None] = mapped_column(Integer)
    completions: Mapped[int | None] = mapped_column(Integer)
    yards: Mapped[float | None] = mapped_column(Float)
    touchdowns: Mapped[int | None] = mapped_column(Integer)
    interceptions: Mapped[int | None] = mapped_column(Integer)
    receptions: Mapped[int | None] = mapped_column(Integer)
    targets: Mapped[int | None] = mapped_column(Integer)
    carries: Mapped[int | None] = mapped_column(Integer)
    fumbles: Mapped[int | None] = mapped_column(Integer)
    tackles: Mapped[float | None] = mapped_column(Float)
    sacks: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )