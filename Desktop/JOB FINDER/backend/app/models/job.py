from datetime import datetime
from sqlalchemy import String, Text, Integer, Float, Boolean, DateTime, JSON, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.database import Base


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(255), index=True)
    company: Mapped[str] = mapped_column(String(255))
    initials: Mapped[str] = mapped_column(String(10), default="")
    color: Mapped[str] = mapped_column(String(20), default="#4F46E5")
    location: Mapped[str] = mapped_column(String(255), default="")
    location_type: Mapped[str] = mapped_column(String(50), default="On-site")
    type: Mapped[str] = mapped_column(String(50), default="Full-time")
    experience: Mapped[str] = mapped_column(String(50), default="Mid")
    salary: Mapped[str] = mapped_column(String(100), default="")
    match_score: Mapped[float] = mapped_column(Float, default=0.0)
    source: Mapped[str] = mapped_column(String(50), default="linkedin")
    posted_days: Mapped[int] = mapped_column(Integer, default=0)
    description: Mapped[str] = mapped_column(Text, default="")
    requirements: Mapped[list] = mapped_column(JSON, default=list)
    matching_skills: Mapped[list] = mapped_column(JSON, default=list)
    missing_skills: Mapped[list] = mapped_column(JSON, default=list)
    tags: Mapped[list] = mapped_column(JSON, default=list)
    # Deduplication: stable ID from the source (e.g. LinkedIn job ID, Rozee job ID).
    # Seeded jobs use "seed:<slug>". Combination of (external_id, source) is unique.
    external_id: Mapped[str] = mapped_column(String(512), default="", index=True)
    url: Mapped[str] = mapped_column(String(1024), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
