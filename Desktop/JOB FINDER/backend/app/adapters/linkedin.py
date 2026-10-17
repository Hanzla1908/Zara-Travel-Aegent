"""
LinkedIn Jobs adapter.

Uses LinkedIn's Partner Jobs API (v2).

Access requirements:
  • Apply for the "Jobs on LinkedIn" partner programme:
    https://developer.linkedin.com/product-catalog/jobs
  • Generate an OAuth 2.0 access token with the `r_job_search` scope.
  • Set LINKEDIN_ACCESS_TOKEN in your .env file.

When the token is absent this adapter returns available=False and an empty
job list — the rest of the application continues normally without LinkedIn data.

API reference:
  GET https://api.linkedin.com/v2/jobPostings
    ?q=jobPostings
    &keywords=<keyword>
    &locationId=<urn>      (LinkedIn geo URN, e.g. urn:li:geo:105149290 for Pakistan)
    &count=<n>
    &start=<offset>
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx

from app.adapters.base import AdapterQuery, AdapterResult, BaseAdapter, RawJob

logger = logging.getLogger(__name__)

_API_BASE = "https://api.linkedin.com/v2"
_TIMEOUT = 15.0


def _parse_location_type(remote_allowed: bool | None, work_place: str) -> str:
    if remote_allowed:
        return "Remote"
    if "hybrid" in work_place.lower():
        return "Hybrid"
    return "On-site"


def _parse_experience(level: str) -> str:
    mapping = {
        "INTERNSHIP":       "Junior",
        "ENTRY_LEVEL":      "Junior",
        "ASSOCIATE":        "Junior",
        "MID_SENIOR_LEVEL": "Mid",
        "DIRECTOR":         "Senior",
        "EXECUTIVE":        "Lead",
        "NOT_APPLICABLE":   "Mid",
    }
    return mapping.get(level.upper(), "Mid")


def _normalize(raw: dict) -> RawJob:
    """Convert a LinkedIn jobPosting entity into a RawJob."""
    jid = str(raw.get("id", ""))
    title = raw.get("title", "")
    company_name = (
        raw.get("companyDetails", {})
           .get("com.linkedin.voyager.jobs.JobPostingCompany", {})
           .get("companyResolutionResult", {})
           .get("name", "")
        or raw.get("formattedName", "")
    )
    location_str = raw.get("formattedLocation", "")
    description_html = (
        raw.get("description", {}).get("text", "")
        if isinstance(raw.get("description"), dict)
        else str(raw.get("description", ""))
    )
    salary_range = raw.get("salaryInsights", {}).get("salaryRange", {})
    salary_str = ""
    if salary_range:
        lo = salary_range.get("min", "")
        hi = salary_range.get("max", "")
        currency = salary_range.get("currencyCode", "")
        if lo and hi:
            salary_str = f"{currency} {lo}–{hi}/yr".strip()

    listed_at_ms = raw.get("listedAt")
    posted_at: datetime | None = None
    if listed_at_ms:
        try:
            posted_at = datetime.fromtimestamp(listed_at_ms / 1000, tz=timezone.utc)
        except Exception:
            pass

    remote_allowed = raw.get("workRemoteAllowed")
    workplace_type = raw.get("workplaceTypes", [""])[0] if raw.get("workplaceTypes") else ""
    exp_level = raw.get("experienceLevel", "MID_SENIOR_LEVEL")

    return RawJob(
        external_id=f"linkedin:{jid}",
        title=title,
        company=company_name,
        location=location_str,
        description=description_html,
        requirements=[],     # LinkedIn's API doesn't return structured requirements
        salary=salary_str,
        source="linkedin",
        url=f"https://www.linkedin.com/jobs/view/{jid}/",
        posted_at=posted_at,
        location_type=_parse_location_type(remote_allowed, workplace_type),
        job_type=raw.get("employmentType", "FULL_TIME").replace("_", " ").title(),
        experience=_parse_experience(exp_level),
    )


class LinkedInAdapter(BaseAdapter):
    source_id = "linkedin"
    source_label = "LinkedIn"

    @property
    def is_configured(self) -> bool:
        from app.config import settings
        return bool(settings.linkedin_access_token)

    async def fetch(self, query: AdapterQuery) -> AdapterResult:
        if not self.is_configured:
            return AdapterResult(
                jobs=[],
                available=False,
                reason=(
                    "LinkedIn adapter is not configured. "
                    "Set LINKEDIN_ACCESS_TOKEN in .env after joining the LinkedIn "
                    "Jobs partner programme: https://developer.linkedin.com/product-catalog/jobs"
                ),
            )

        from app.config import settings

        params: dict[str, str | int] = {
            "q": "jobPostings",
            "count": min(query.limit, 50),
            "start": 0,
        }
        if query.keyword:
            params["keywords"] = query.keyword
        if query.location:
            # Free-text location; partner accounts can also pass a geoUrn
            params["location"] = query.location
        if query.job_type:
            et_map = {
                "Full-time": "FULL_TIME",
                "Part-time": "PART_TIME",
                "Contract":  "CONTRACT",
                "Remote":    "FULL_TIME",
            }
            et = et_map.get(query.job_type, "FULL_TIME")
            params["f_E"] = et

        headers = {
            "Authorization": f"Bearer {settings.linkedin_access_token}",
            "X-Restli-Protocol-Version": "2.0.0",
            "LinkedIn-Version": "202304",
        }

        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.get(
                    f"{_API_BASE}/jobPostings",
                    headers=headers,
                    params=params,
                )

            if resp.status_code == 401:
                logger.warning("LinkedIn: invalid or expired access token.")
                return AdapterResult(
                    jobs=[],
                    available=False,
                    reason="LinkedIn access token is invalid or expired. Renew it in your LinkedIn app.",
                )
            if resp.status_code == 403:
                logger.warning("LinkedIn: access denied — partner programme access required.")
                return AdapterResult(
                    jobs=[],
                    available=False,
                    reason=(
                        "LinkedIn returned 403 Forbidden. "
                        "Your app may not have Jobs partner programme access."
                    ),
                )
            resp.raise_for_status()

            data = resp.json()
            elements = data.get("elements", [])
            jobs = []
            for el in elements:
                try:
                    jobs.append(_normalize(el))
                except Exception:
                    logger.debug("LinkedIn: skipped malformed job element.")

            return AdapterResult(jobs=jobs, available=True)

        except httpx.TimeoutException:
            logger.warning("LinkedIn: request timed out.")
            return AdapterResult(
                jobs=[],
                available=False,
                reason="LinkedIn API timed out. Will retry on next refresh.",
            )
        except Exception as exc:
            logger.warning("LinkedIn fetch error: %s", exc)
            return AdapterResult(
                jobs=[],
                available=False,
                reason=f"LinkedIn source temporarily unavailable: {type(exc).__name__}",
            )
