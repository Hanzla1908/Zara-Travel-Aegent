"""
Adapter registry: runs all configured job-source adapters, deduplicates results
against the database, and upserts new jobs.

Security notes:
  - Never invents jobs or returns data not received from a live source.
  - raw.external_id must be a non-empty "<source>:<id>" string; rows with a
    blank or malformed id are skipped rather than saved.
  - No personal data is stored beyond what the source API returns.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.base import AdapterQuery, BaseAdapter, RawJob
from app.adapters.linkedin import LinkedInAdapter
from app.adapters.rozee import RozeeAdapter
from app.models.job import Job

logger = logging.getLogger(__name__)

_ADAPTERS: list[BaseAdapter] = [
    LinkedInAdapter(),
    RozeeAdapter(),
]

_SOURCE_COLORS: dict[str, str] = {
    "linkedin": "#0077B5",
    "rozee":    "#E31E24",
}


def _initials(company: str) -> str:
    words = [w for w in company.split() if w]
    if not words:
        return "?"
    if len(words) == 1:
        return words[0][:2].upper()
    return (words[0][0] + words[1][0]).upper()


def _posted_days(posted_at: datetime | None) -> int:
    if posted_at is None:
        return 0
    now = datetime.now(timezone.utc)
    if posted_at.tzinfo is None:
        posted_at = posted_at.replace(tzinfo=timezone.utc)
    delta = now - posted_at
    return max(0, delta.days)


def _raw_to_job(raw: RawJob) -> Job:
    return Job(
        external_id=raw.external_id,
        title=raw.title,
        company=raw.company,
        initials=_initials(raw.company),
        color=_SOURCE_COLORS.get(raw.source, "#4F46E5"),
        location=raw.location,
        location_type=raw.location_type,
        type=raw.job_type,
        experience=raw.experience,
        salary=raw.salary,
        match_score=0.0,
        source=raw.source,
        posted_days=_posted_days(raw.posted_at),
        description=raw.description,
        requirements=raw.requirements,
        matching_skills=[],
        missing_skills=[],
        tags=[],
        url=raw.url,
    )


async def run_adapters(
    db: AsyncSession,
    query: AdapterQuery,
    sources: list[str] | None = None,
) -> dict:
    """
    Run registered adapters, deduplicate against the DB, and save new jobs.

    *sources*: list of source_id strings to restrict which adapters run.
               None / empty → all adapters run.

    Returns:
        {
            "fetched":  {"linkedin": 40, "rozee": 0},
            "saved":    12,
            "skipped":  28,
            "errors":   {"rozee": "Rozee.pk adapter is not configured. ..."},
        }
    """
    fetched: dict[str, int] = {}
    errors: dict[str, str] = {}
    saved = 0
    skipped = 0

    adapters_to_run: list[BaseAdapter] = [
        a for a in _ADAPTERS
        if not sources or a.source_id in sources
    ]

    for adapter in adapters_to_run:
        result = await adapter.fetch(query)

        if not result.available:
            errors[adapter.source_id] = result.reason
            fetched[adapter.source_id] = 0
            continue

        fetched[adapter.source_id] = len(result.jobs)

        for raw in result.jobs:
            # Skip any job with a blank or malformed external_id.
            if not raw.external_id or ":" not in raw.external_id:
                skipped += 1
                continue
            _, sep, after = raw.external_id.partition(":")
            if not after.strip():
                skipped += 1
                continue

            existing = await db.execute(
                select(Job).where(
                    Job.external_id == raw.external_id,
                    Job.source == raw.source,
                )
            )
            if existing.scalar_one_or_none() is not None:
                skipped += 1
                continue

            db.add(_raw_to_job(raw))
            saved += 1

    if saved:
        await db.commit()

    return {
        "fetched": fetched,
        "saved":   saved,
        "skipped": skipped,
        "errors":  errors,
    }
