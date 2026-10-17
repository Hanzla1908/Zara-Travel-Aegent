"""
Rozee.pk Jobs adapter.

Uses the Rozee.pk Partner/Employer API.

Access requirements:
  • Register as an employer or partner at https://www.rozee.pk/
  • Request API access by emailing api@rozee.pk or via the employer dashboard.
  • Set ROZEE_API_KEY in your .env file.
  • Optionally override ROZEE_API_BASE (default: https://api.rozee.pk/v1).

When the API key is absent this adapter returns available=False and an empty
job list — the rest of the application continues normally without Rozee data.

API reference (once access is granted):
  GET <ROZEE_API_BASE>/jobs/search
    ?keyword=<keyword>
    &location=<city>
    &job_type=<Full-time|Part-time|Contract>
    &experience=<1|2|3>      (1=Junior, 2=Mid, 3=Senior)
    &limit=<n>
    &page=<n>
    &api_key=<ROZEE_API_KEY>

  Expected response envelope:
  {
    "status": "success",
    "total": 120,
    "jobs": [
      {
        "id": "...",
        "title": "...",
        "company": { "name": "...", "logo": "..." },
        "location": { "city": "...", "country": "..." },
        "description": "...",
        "skills": ["..."],
        "salary_min": 100000,
        "salary_max": 150000,
        "salary_currency": "PKR",
        "salary_period": "monthly",
        "job_type": "Full-time",
        "experience_level": "Mid",
        "workplace_type": "On-site",
        "posted_at": "2024-01-15T10:00:00Z",
        "url": "https://www.rozee.pk/job/..."
      }
    ]
  }
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx

from app.adapters.base import AdapterQuery, AdapterResult, BaseAdapter, RawJob

logger = logging.getLogger(__name__)
_TIMEOUT = 15.0


def _salary_str(raw: dict) -> str:
    lo  = raw.get("salary_min")
    hi  = raw.get("salary_max")
    cur = raw.get("salary_currency", "PKR")
    per = raw.get("salary_period", "monthly")
    if lo and hi:
        period_label = {"monthly": "mo", "annual": "yr"}.get(per, per)
        return f"{cur} {lo:,}–{hi:,}/{period_label}"
    if lo:
        return f"{cur} {lo:,}/{per}"
    return ""


def _location_type(workplace: str) -> str:
    wl = workplace.lower()
    if "remote" in wl:
        return "Remote"
    if "hybrid" in wl:
        return "Hybrid"
    return "On-site"


def _experience(level: str) -> str:
    mapping = {
        "junior":  "Junior",
        "entry":   "Junior",
        "mid":     "Mid",
        "senior":  "Senior",
        "lead":    "Lead",
        "manager": "Lead",
    }
    return mapping.get(level.lower(), "Mid")


def _posted_at(raw: dict) -> datetime | None:
    iso = raw.get("posted_at")
    if not iso:
        return None
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except Exception:
        return None


def _normalize(raw: dict) -> RawJob:
    """Convert a Rozee API job object into a RawJob."""
    jid = str(raw.get("id", ""))

    company_info = raw.get("company", {})
    company_name = (
        company_info.get("name", "") if isinstance(company_info, dict) else str(company_info)
    )

    location_info = raw.get("location", {})
    if isinstance(location_info, dict):
        city    = location_info.get("city", "")
        country = location_info.get("country", "Pakistan")
        location_str = f"{city}, {country}".strip(", ")
    else:
        location_str = str(location_info)

    skills = raw.get("skills", [])
    requirements = [f"Skill: {s}" for s in skills] if skills else []

    url = raw.get("url", f"https://www.rozee.pk/job/{jid}")

    return RawJob(
        external_id=f"rozee:{jid}",
        title=raw.get("title", ""),
        company=company_name,
        location=location_str,
        description=raw.get("description", ""),
        requirements=requirements,
        salary=_salary_str(raw),
        source="rozee",
        url=url,
        posted_at=_posted_at(raw),
        location_type=_location_type(raw.get("workplace_type", "On-site")),
        job_type=raw.get("job_type", "Full-time"),
        experience=_experience(raw.get("experience_level", "mid")),
    )


class RozeeAdapter(BaseAdapter):
    source_id = "rozee"
    source_label = "Rozee.pk"

    @property
    def is_configured(self) -> bool:
        from app.config import settings
        return bool(settings.rozee_api_key)

    async def fetch(self, query: AdapterQuery) -> AdapterResult:
        if not self.is_configured:
            return AdapterResult(
                jobs=[],
                available=False,
                reason=(
                    "Rozee.pk adapter is not configured. "
                    "Set ROZEE_API_KEY in .env after requesting API access "
                    "at https://www.rozee.pk/ (email api@rozee.pk)."
                ),
            )

        from app.config import settings

        params: dict[str, str | int] = {
            "api_key": settings.rozee_api_key,
            "limit":   min(query.limit, 50),
            "page":    1,
        }
        if query.keyword:
            params["keyword"] = query.keyword
        if query.location:
            params["location"] = query.location
        if query.job_type:
            params["job_type"] = query.job_type
        if query.experience:
            exp_map = {"Junior": "1", "Mid": "2", "Senior": "3", "Lead": "3"}
            exps = [exp_map.get(e, "2") for e in query.experience]
            params["experience"] = exps[0] if exps else "2"

        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.get(
                    f"{settings.rozee_api_base}/jobs/search",
                    params=params,
                )

            if resp.status_code == 401:
                logger.warning("Rozee: invalid API key.")
                return AdapterResult(
                    jobs=[],
                    available=False,
                    reason="Rozee.pk API key is invalid. Check ROZEE_API_KEY in .env.",
                )
            if resp.status_code == 403:
                logger.warning("Rozee: access denied.")
                return AdapterResult(
                    jobs=[],
                    available=False,
                    reason="Rozee.pk API returned 403. Verify your API access level.",
                )
            resp.raise_for_status()

            data = resp.json()
            if data.get("status") != "success":
                logger.warning("Rozee: unexpected response status: %s", data.get("status"))
                return AdapterResult(
                    jobs=[],
                    available=False,
                    reason=f"Rozee.pk returned status: {data.get('status', 'unknown')}",
                )

            jobs = []
            for el in data.get("jobs", []):
                try:
                    jobs.append(_normalize(el))
                except Exception:
                    logger.debug("Rozee: skipped malformed job element.")

            return AdapterResult(jobs=jobs, available=True)

        except httpx.TimeoutException:
            logger.warning("Rozee: request timed out.")
            return AdapterResult(
                jobs=[],
                available=False,
                reason="Rozee.pk API timed out. Will retry on next refresh.",
            )
        except Exception as exc:
            logger.warning("Rozee fetch error: %s", exc)
            return AdapterResult(
                jobs=[],
                available=False,
                reason=f"Rozee.pk source temporarily unavailable: {type(exc).__name__}",
            )
