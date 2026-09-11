from datetime import datetime

from sqlalchemy import String, Integer, DateTime, ForeignKey, Date, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Game(Base):
    __tablename__ = "games"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    external_id: Mapped[str] = mapped_column(String(50), nullable=False)
    league: Mapped[str] = mapped_column(String(10), nullable=False)
    season: Mapped[int] = mapped_column(Integer, nullable=False)
    week: Mapped[int | None] = mapped_column(Integer)
    # Two foreign keys for the two teams playing
    home_team_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("teams.id", ondelete="SET NULL")
    )
    away_team_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("teams.id", ondelete="SET NULL")
    )
    # Nullable because a game might be scheduled but not yet played
    home_score: Mapped[int | None] = mapped_column(Integer)
    away_score: Mapped[int | None] = mapped_column(Integer)
    game_date: Mapped[datetime | None] = mapped_column(Date)
    # "scheduled", "in_progress", "final"
    status: Mapped[str | None] = mapped_column(String(20))
    venue: Mapped[str | None] = mapped_column(String(150))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )