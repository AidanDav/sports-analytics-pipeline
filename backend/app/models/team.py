from datetime import datetime

from sqlalchemy import String, Integer, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Team(Base):
    __tablename__ = "teams"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Which source this record came from: "cfbd" or "highlightly"
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    # The ID used by the original API, so we can match updates later
    external_id: Mapped[str] = mapped_column(String(50), nullable=False)
    # "cfb" or "nfl"
    league: Mapped[str] = mapped_column(String(10), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    abbreviation: Mapped[str | None] = mapped_column(String(20))
    conference: Mapped[str | None] = mapped_column(String(50))
    # Tracks when records were created and last updated
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )