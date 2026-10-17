"""
Search Agent — wraps the adapter registry with timeout and retry logic.

Never invents jobs; only returns data received from configured sources.
Unavailable or unconfigured adapters are reported in the errors dict
without raising so the coordinator can proceed with partial results.
"""

from __future__ import annotations

import asyncio
import logging

from app.adapters.base import AdapterQuery

logger = logging.getLogger(__name__)

_PER_ADAPTER_TIMEOUT = 20   # seconds
_MAX_RETRIES         = 2


class SearchAgent:
    """Fetch jobs from all configured adapters with timeout + retry."""

    async def run(
        self,
        keyword:    str        = "",
        location:   str        = "",
        sources:    list[str] | None = None,
        experience: list[str] | None = None,
        job_type:   str        = "",
        limit:      int        = 20,
    ) -> dict:
        """
        Run configured adapters and collect raw job dicts.

        Args:
            sources: list of source_id strings to restrict to, or None for all.

        Returns a dict with keys:
            jobs    — list of raw job dicts (never invented)
            fetched — {source_id: count} for every adapter attempted
            errors  — {source_id: reason_string} for every failure
        """
        from app.adapters.registry import _ADAPTERS

        query = AdapterQuery(
            keyword=keyword,
            location=location,
            experience=experience or [],
            job_type=job_type,
            limit=limit,
        )

        adapters_to_run = [
            a for a in _ADAPTERS
            if sources is None or a.source_id in sources
        ]

        fetched: dict[str, int]  = {}
        errors:  dict[str, str]  = {}
        all_jobs: list[dict]     = []

        for adapter in adapters_to_run:
            result = await self._fetch_with_retry(adapter, query)
            fetched[adapter.source_id] = result.get("count", 0)
            if "error" in result:
                errors[adapter.source_id] = result["error"]
            else:
                all_jobs.extend(result.get("jobs", []))

        return {"jobs": all_jobs, "fetched": fetched, "errors": errors}

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _fetch_with_retry(self, adapter, query: AdapterQuery) -> dict:
        last_error: str = ""
        for attempt in range(_MAX_RETRIES):
            try:
                result = await asyncio.wait_for(
                    adapter.fetch(query), timeout=_PER_ADAPTER_TIMEOUT
                )
                if not result.available:
                    return {"count": 0, "jobs": [], "error": result.reason}
                jobs = [self._raw_to_dict(j) for j in result.jobs]
                return {"count": len(jobs), "jobs": jobs}
            except asyncio.TimeoutError:
                last_error = f"Timed out after {_PER_ADAPTER_TIMEOUT}s"
                logger.warning("Adapter %s timed out (attempt %d)", adapter.source_id, attempt + 1)
            except Exception as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                logger.warning("Adapter %s error on attempt %d: %s", adapter.source_id, attempt + 1, exc)
                if attempt < _MAX_RETRIES - 1:
                    await asyncio.sleep(1.0 * (attempt + 1))

        return {"count": 0, "jobs": [], "error": last_error}

    @staticmethod
    def _raw_to_dict(raw) -> dict:
        return {
            "external_id":   raw.external_id,
            "title":         raw.title,
            "company":       raw.company,
            "location":      raw.location,
            "description":   raw.description,
            "requirements":  raw.requirements,
            "salary":        raw.salary,
            "source":        raw.source,
            "url":           raw.url,
            "location_type": raw.location_type,
            "job_type":      raw.job_type,
            "experience":    raw.experience,
        }
