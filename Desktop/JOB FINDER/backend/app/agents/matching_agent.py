"""
Matching Agent — wraps the deterministic rank_jobs scorer.

Scoring is always pure Python; Claude is only invoked for prose explanations
when the caller explicitly sets explain=True.
"""

from __future__ import annotations

import asyncio
import logging

from app.services.matcher import DEFAULT_WEIGHTS, MatchWeights, rank_jobs

logger = logging.getLogger(__name__)

_MATCH_TIMEOUT = 30  # seconds for the full ranking pass


class MatchingAgent:
    """Score and rank a list of job dicts against a CV profile dict."""

    async def run(
        self,
        cv:      dict,
        jobs:    list[dict],
        weights: MatchWeights = DEFAULT_WEIGHTS,
        explain: bool         = False,
    ) -> list[dict]:
        """
        Return job match summaries sorted by score descending.

        Args:
            cv:      CV profile dict (skills, experience_years, job_titles, location).
            jobs:    List of job dicts (id, title, requirements, description, …).
            weights: Score component weights (must sum to 1.0).
            explain: Generate Claude prose explanations (costs API tokens).

        Returns:
            List of dicts: job_id, score, breakdown, matched_skills,
            missing_skills, reasons, explanation.
        """
        if not jobs:
            return []

        try:
            results = await asyncio.wait_for(
                rank_jobs(cv, jobs, weights, explain=explain),
                timeout=_MATCH_TIMEOUT,
            )
        except asyncio.TimeoutError:
            logger.warning("rank_jobs timed out after %ds — returning empty.", _MATCH_TIMEOUT)
            return []

        return [
            {
                "job_id":         r.job_id,
                "score":          r.score,
                "breakdown": {
                    "skills":     r.breakdown.skills,
                    "experience": r.breakdown.experience,
                    "title":      r.breakdown.title,
                    "location":   r.breakdown.location,
                },
                "matched_skills": r.matched_skills,
                "missing_skills": r.missing_skills,
                "reasons":        r.reasons,
                "explanation":    r.explanation,
            }
            for r in results
        ]
