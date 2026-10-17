from datetime import datetime
from sqlalchemy import String, Integer, Float, Boolean, DateTime, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.database import Base


class AlertNotification(Base):
    """One row per (alert_id, job_external_id) — the deduplication gate."""

    __tablename__ = "alert_notifications"

    id:              Mapped[int]           = mapped_column(Integer, primary_key=True, autoincrement=True)
    alert_id:        Mapped[int]           = mapped_column(Integer, index=True)
    user_id:         Mapped[str]           = mapped_column(String(100), index=True)
    job_external_id: Mapped[str]           = mapped_column(String(512))
    job_id:          Mapped[int | None]    = mapped_column(Integer, nullable=True)
    job_title:       Mapped[str]           = mapped_column(String(255), default="")
    company:         Mapped[str]           = mapped_column(String(255), default="")
    score:           Mapped[float]         = mapped_column(Float, default=0.0)
    seen:            Mapped[bool]          = mapped_column(Boolean, default=False)
    created_at:      Mapped[datetime]      = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("alert_id", "job_external_id", name="uq_alert_job"),
    )
