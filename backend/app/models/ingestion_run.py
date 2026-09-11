from datetime import datetime

from sqlalchemy import String, Integer, DateTime, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

#Observability Layer: This table tracks the ingestion runs for each source and data type. 
# It records the status of the run, how many rows were created, updated, or skipped, and 
# any error messages if the run failed. This allows us to monitor the health of our data ingestion 
# process and identify any issues that may arise.
class IngestionRun(Base):
    __tablename__ = "ingestion_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Which source was pulled: "cfbd" or "highlightly"
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    # What type of data: "teams", "players", "games", "stats"
    data_type: Mapped[str] = mapped_column(String(30), nullable=False)
    # "running", "success", "failed"
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    # How many rows were created, updated, or skipped
    rows_created: Mapped[int] = mapped_column(Integer, default=0)
    rows_updated: Mapped[int] = mapped_column(Integer, default=0)
    rows_skipped: Mapped[int] = mapped_column(Integer, default=0)
    # If it failed, store the error message
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))