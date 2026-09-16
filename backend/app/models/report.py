from datetime import datetime

from sqlalchemy import String, Integer, DateTime, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # "weekly_summary", "player_spotlight", "team_breakdown"
    report_type: Mapped[str] = mapped_column(String(30), nullable=False)
    # Human-readable title like "Week 1 NFL Summary"
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    # The full generated report content (markdown)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # The prompt we sent to Claude, stored for debugging and iteration
    prompt_used: Mapped[str] = mapped_column(Text, nullable=False)
    # Which model generated it
    model: Mapped[str] = mapped_column(String(50), nullable=False)
    # "generating", "complete", "failed"
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    # Optional context: what season/week this covers
    season: Mapped[int | None] = mapped_column(Integer)
    week: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )