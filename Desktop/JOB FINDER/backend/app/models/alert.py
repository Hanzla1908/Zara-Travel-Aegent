from datetime import datetime
from sqlalchemy import String, Integer, Float, Boolean, DateTime, JSON, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.database import Base


class JobAlert(Base):
    __tablename__ = "job_alerts"

    id:            Mapped[int]          = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id:       Mapped[str]          = mapped_column(String(100), default="default", index=True)
    name:          Mapped[str]          = mapped_column(String(255))
    keywords:      Mapped[str]          = mapped_column(String(500))
    location:      Mapped[str]          = mapped_column(String(255), default="")
    frequency:     Mapped[str]          = mapped_column(String(50), default="Daily")
    sources:       Mapped[list]         = mapped_column(JSON, default=list)
    active:        Mapped[bool]         = mapped_column(Boolean, default=True)
    # Minimum match score (0–100) a job must reach before a notification is created.
    min_score:     Mapped[float]        = mapped_column(Float, default=0.0)
    # Email delivery — only used when SMTP is configured server-side.
    email_enabled: Mapped[bool]         = mapped_column(Boolean, default=False)
    email_address: Mapped[str]          = mapped_column(String(255), default="")
    # Set after each successful check run.
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at:    Mapped[datetime]     = mapped_column(DateTime, server_default=func.now())
