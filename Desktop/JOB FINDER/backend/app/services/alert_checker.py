"""
Alert checker — runs due job alerts and creates AlertNotification rows.

Security constraints:
  - Adapter calls happen only for alerts that have external sources listed.
  - A notification is created at most once per (alert_id, job_external_id) pair.
  - Email is only sent when email_enabled=True AND SMTP is configured in settings.
    No email is ever sent without both conditions.
  - Raw CV text is never logged or passed to external services.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.alert import JobAlert
from app.models.alert_notification import AlertNotification
from app.models.cv_profile import CVProfile
from app.models.job import Job
from app.services.matcher import DEFAULT_WEIGHTS, calculate_match

logger = logging.getLogger(__name__)

_FREQUENCY_HOURS: dict[str, int] = {
    "Hourly":  1,
    "Daily":   24,
    "Weekly":  168,
}
_ADAPTER_TIMEOUT = 20  # seconds per source


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------

async def check_all_due_alerts(db: AsyncSession) -> dict[int, int]:
    """
    Check every active alert that is due for its next run.

    Returns {alert_id: new_notification_count} for alerts that produced
    at least one new notification.
    """
    now = datetime.utcnow()
    result = await db.execute(
        select(JobAlert).where(JobAlert.active == True)  # noqa: E712
    )
    alerts: list[JobAlert] = list(result.scalars().all())

    counts: dict[int, int] = {}
    for alert in alerts:
        if _is_due(alert, now):
            try:
                n = await check_alert(db, alert)
                if n:
                    counts[alert.id] = n
            except Exception as exc:
                logger.warning("Alert %d check failed: %s", alert.id, exc)
    return counts


async def check_alert(db: AsyncSession, alert: JobAlert) -> int:
    """
    Run one alert: score matching jobs, persist new notifications.

    Returns the count of new notifications created.
    """
    cv = await _load_cv(db, alert.user_id)
    if cv is None:
        logger.debug("Alert %d skipped — no CV for user %r.", alert.id, alert.user_id)
        _update_checked(alert)
        await db.commit()
        return 0

    jobs = await _gather_jobs(db, alert)
    if not jobs:
        _update_checked(alert)
        await db.commit()
        return 0

    scored = _score_and_filter(cv, jobs, alert.min_score)
    new_count = await _persist_notifications(db, alert, scored)

    _update_checked(alert)
    await db.commit()

    if new_count:
        logger.info(
            "Alert %d (%r): %d new notification(s) (min_score=%.0f).",
            alert.id, alert.name, new_count, alert.min_score,
        )
        if alert.email_enabled and alert.email_address:
            await _maybe_send_email(alert, new_count)

    return new_count


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _is_due(alert: JobAlert, now: datetime) -> bool:
    if alert.last_checked_at is None:
        return True
    interval = timedelta(hours=_FREQUENCY_HOURS.get(alert.frequency, 24))
    return (now - alert.last_checked_at) >= interval


def _update_checked(alert: JobAlert) -> None:
    alert.last_checked_at = datetime.utcnow()


async def _load_cv(db: AsyncSession, user_id: str) -> dict | None:
    result = await db.execute(
        select(CVProfile)
        .where(CVProfile.user_id == user_id)
        .order_by(CVProfile.uploaded_at.desc())
        .limit(1)
    )
    profile = result.scalar_one_or_none()
    if profile is None:
        return None
    return {
        "skills":           profile.skills           or [],
        "experience_years": profile.experience_years or 0,
        "job_titles":       profile.job_titles        or [],
        "location":         profile.location          or "",
    }


async def _gather_jobs(db: AsyncSession, alert: JobAlert) -> list[dict]:
    """Load DB jobs + adapter jobs. Adapter call only when sources are listed."""
    db_jobs = await _load_db_jobs(db, alert)
    adapter_jobs = await _search_adapters(alert)
    return _deduplicate(db_jobs + adapter_jobs)


async def _load_db_jobs(db: AsyncSession, alert: JobAlert) -> list[dict]:
    from sqlalchemy import or_
    stmt = select(Job)
    if alert.keywords:
        kw = f"%{alert.keywords}%"
        stmt = stmt.where(
            or_(Job.title.ilike(kw), Job.description.ilike(kw), Job.company.ilike(kw))
        )
    if alert.location:
        loc = f"%{alert.location}%"
        stmt = stmt.where(or_(Job.location.ilike(loc), Job.location_type.ilike(loc)))
    rows = (await db.execute(stmt)).scalars().all()
    return [{c.name: getattr(j, c.name) for c in j.__table__.columns} for j in rows]


async def _search_adapters(alert: JobAlert) -> list[dict]:
    """Run configured adapters for this alert's sources. Never raises."""
    if not alert.sources:
        return []
    try:
        import asyncio
        from app.adapters.base import AdapterQuery
        from app.adapters.registry import _ADAPTERS

        query = AdapterQuery(keyword=alert.keywords, location=alert.location or "")
        jobs: list[dict] = []
        for adapter in _ADAPTERS:
            if adapter.source_id not in alert.sources:
                continue
            try:
                result = await asyncio.wait_for(adapter.fetch(query), timeout=_ADAPTER_TIMEOUT)
                if result.available:
                    for raw in result.jobs:
                        jobs.append({
                            "external_id":   raw.external_id,
                            "title":         raw.title,
                            "company":       raw.company,
                            "location":      raw.location,
                            "description":   raw.description,
                            "requirements":  raw.requirements,
                            "experience":    raw.experience,
                            "location_type": raw.location_type,
                            "salary":        raw.salary,
                            "source":        raw.source,
                            "url":           raw.url,
                        })
            except Exception as exc:
                logger.warning("Adapter %s failed for alert %d: %s", adapter.source_id, alert.id, exc)
        return jobs
    except Exception as exc:
        logger.warning("Adapter search error for alert %d: %s", alert.id, exc)
        return []


def _deduplicate(jobs: list[dict]) -> list[dict]:
    seen: set[str] = set()
    out:  list[dict] = []
    for j in jobs:
        key = j.get("external_id") or f"id:{j.get('id', id(j))}"
        if key not in seen:
            seen.add(key)
            out.append(j)
    return out


def _score_and_filter(
    cv: dict, jobs: list[dict], min_score: float
) -> list[tuple[dict, float]]:
    """Score each job; return (job_dict, score) pairs that meet min_score."""
    scored: list[tuple[dict, float]] = []
    for job in jobs:
        result = calculate_match(cv, job, DEFAULT_WEIGHTS)
        if result.score >= min_score:
            scored.append((job, result.score))
    scored.sort(key=lambda p: p[1], reverse=True)
    return scored


async def _persist_notifications(
    db: AsyncSession,
    alert: JobAlert,
    scored: list[tuple[dict, float]],
) -> int:
    """Insert new AlertNotification rows; skip any (alert_id, external_id) already seen."""
    new_count = 0
    for job, score in scored:
        ext_id = job.get("external_id") or f"id:{job.get('id', '')}"

        # Check for existing notification before insert to avoid IntegrityError in most cases.
        exists = (await db.execute(
            select(AlertNotification).where(
                AlertNotification.alert_id == alert.id,
                AlertNotification.job_external_id == ext_id,
            )
        )).scalar_one_or_none()

        if exists:
            continue

        try:
            # Use a savepoint so a concurrent duplicate only rolls back this one row.
            async with db.begin_nested():
                db.add(AlertNotification(
                    alert_id=alert.id,
                    user_id=alert.user_id,
                    job_external_id=ext_id,
                    job_id=job.get("id"),
                    job_title=job.get("title", ""),
                    company=job.get("company", ""),
                    score=round(score, 1),
                ))
            new_count += 1
        except IntegrityError:
            # A concurrent request beat us to this (alert, job) pair — silently skip.
            pass

    return new_count


async def _maybe_send_email(alert: JobAlert, new_count: int) -> None:
    """
    Send an email notification if SMTP is configured server-side.

    No email is sent without:
      1. alert.email_enabled == True  (user opted in)
      2. alert.email_address set      (user provided address)
      3. SMTP_HOST configured in .env (server admin set up outbound mail)
    """
    try:
        from app.config import settings
        smtp_host = getattr(settings, "smtp_host", "")
        if not smtp_host:
            logger.info(
                "Alert %d: email_enabled but SMTP not configured — skipping delivery.  "
                "Set SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, SMTP_FROM in .env to enable.",
                alert.id,
            )
            return

        import smtplib
        from email.message import EmailMessage

        msg = EmailMessage()
        msg["Subject"] = f"[Job Alert] {new_count} new match(es) for \"{alert.name}\""
        msg["From"]    = getattr(settings, "smtp_from", settings.smtp_user)
        msg["To"]      = alert.email_address
        msg.set_content(
            f"Your job alert \"{alert.name}\" found {new_count} new matching job(s).\n\n"
            f"Log in to view your results at GET /api/alerts/{alert.id}/results\n\n"
            "Reply to this email to unsubscribe, or set email_enabled=false on your alert."
        )
        with smtplib.SMTP(settings.smtp_host, getattr(settings, "smtp_port", 587)) as smtp:
            smtp.starttls()
            if getattr(settings, "smtp_user", ""):
                smtp.login(settings.smtp_user, settings.smtp_pass)
            smtp.send_message(msg)
        logger.info("Email sent to %s for alert %d.", alert.email_address, alert.id)
    except Exception as exc:
        logger.warning("Email delivery failed for alert %d: %s", alert.id, exc)
