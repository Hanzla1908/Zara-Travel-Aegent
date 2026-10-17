"""
CV Analysis Agent — fetches the user's parsed CV profile from the database.

Returns None when no CV has been uploaded; callers must handle that case.
Raw CV text is never exposed; only structured fields are returned.
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.cv_profile import CVProfile

logger = logging.getLogger(__name__)


class CVAnalysisAgent:
    """Read the user's CV profile from the database."""

    async def run(self, user_id: str, db: AsyncSession) -> dict | None:
        """
        Return a structured CV dict for *user_id*, or None if not found.

        Returned keys:
            skills           — list[str]
            experience_years — int
            job_titles       — list[str]
            location         — str
            education        — str
            profile_strength — int (0–100)
        """
        result = await db.execute(
            select(CVProfile)
            .where(CVProfile.user_id == user_id)
            .order_by(CVProfile.uploaded_at.desc())
            .limit(1)
        )
        profile = result.scalar_one_or_none()
        if profile is None:
            logger.debug("No CV profile found for user_id=%r", user_id)
            return None
        return {
            "skills":           profile.skills           or [],
            "experience_years": profile.experience_years or 0,
            "job_titles":       profile.job_titles        or [],
            "location":         profile.location          or "",
            "education":        profile.education         or "",
            "profile_strength": profile.profile_strength  or 0,
        }
