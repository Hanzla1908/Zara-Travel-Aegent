"""
Job-search tool — thin wrapper over SearchAgent for one-shot callers.
"""

from __future__ import annotations


async def search_jobs(
    query:    str,
    location: str | None = None,
    sources:  list[str] | None = None,
    limit:    int = 20,
) -> list[dict]:
    """
    Search configured job sources for *query* and return raw job dicts.

    Args:
        query:    Keyword / job-title string.
        location: Optional location filter.
        sources:  Restrict to these source_ids, or None for all.
        limit:    Maximum results per source.

    Returns:
        List of raw job dicts.  Never invents jobs; unavailable sources
        are silently skipped (their errors appear in SearchAgent logs).
    """
    from app.agents.search_agent import SearchAgent

    agent = SearchAgent()
    result = await agent.run(
        keyword=query,
        location=location or "",
        sources=sources,
        limit=limit,
    )
    return result.get("jobs", [])
