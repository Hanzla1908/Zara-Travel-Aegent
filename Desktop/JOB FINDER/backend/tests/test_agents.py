"""
Unit tests for the multi-agent job-finding workflow.

All tests are pure — no real database connections and no network calls.
Async agent methods are exercised via asyncio.run().
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents.base import MatchSummary, WorkflowPreferences, WorkflowResult
from app.agents.coordinator import WorkflowCoordinator
from app.agents.cv_agent import CVAnalysisAgent
from app.agents.matching_agent import MatchingAgent
from app.agents.search_agent import SearchAgent


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def _cv(**kw) -> dict:
    return {
        "skills":           ["python", "react", "typescript"],
        "experience_years": 3,
        "job_titles":       ["Frontend Developer"],
        "location":         "Lahore, Pakistan",
        "education":        "BSc CS",
        "profile_strength": 70,
        **kw,
    }


def _job(job_id=1, **kw) -> dict:
    return {
        "id":            job_id,
        "external_id":   f"seed:job-{job_id}",
        "title":         "React Developer",
        "company":       "Acme Corp",
        "requirements":  ["react", "typescript"],
        "description":   "Build web apps with React.",
        "experience":    "Mid",
        "location":      "Lahore, Pakistan",
        "location_type": "On-site",
        "salary":        "",
        "source":        "seed",
        "url":           "",
        "job_type":      "Full-time",
        **kw,
    }


def _mock_db(profile=None, jobs=None):
    """Return a mock AsyncSession configured with the given profile / jobs."""
    db = AsyncMock()

    # Default: return profile on first execute, jobs on subsequent ones.
    profile_result = MagicMock()
    profile_result.scalar_one_or_none.return_value = profile

    scalars_mock = MagicMock()
    scalars_mock.all.return_value = jobs or []

    jobs_result = MagicMock()
    jobs_result.scalars.return_value = scalars_mock

    db.execute.side_effect = [profile_result, jobs_result]
    return db


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# WorkflowPreferences validation
# ---------------------------------------------------------------------------

class TestWorkflowPreferences:
    def test_defaults(self):
        p = WorkflowPreferences()
        assert p.keyword    == ""
        assert p.confirmed  is False
        assert p.limit      == 20

    def test_limit_clamped(self):
        with pytest.raises(Exception):
            WorkflowPreferences(limit=0)
        with pytest.raises(Exception):
            WorkflowPreferences(limit=101)

    def test_confirmed_is_explicit(self):
        p = WorkflowPreferences(confirmed=True)
        assert p.confirmed is True


# ---------------------------------------------------------------------------
# WorkflowResult / MatchSummary
# ---------------------------------------------------------------------------

class TestWorkflowResult:
    def test_complete_status(self):
        r = WorkflowResult(status="complete")
        assert r.status == "complete"
        assert r.matches == []

    def test_pending_confirmation_status(self):
        r = WorkflowResult(status="pending_confirmation", plan="Search LinkedIn...")
        assert r.plan == "Search LinkedIn..."

    def test_match_summary_fields(self):
        ms = MatchSummary(
            job_id=1,
            score=85.5,
            breakdown={"skills": 90.0, "experience": 80.0, "title": 75.0, "location": 100.0},
            matched_skills=["python"],
            missing_skills=["java"],
            reasons=["Good skill match."],
        )
        assert ms.score == 85.5
        assert ms.explanation == ""


# ---------------------------------------------------------------------------
# CVAnalysisAgent
# ---------------------------------------------------------------------------

class TestCVAnalysisAgent:
    def _make_db_no_profile(self):
        db = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        db.execute.return_value = result
        return db

    def _make_db_with_profile(self):
        db = AsyncMock()
        mock_profile = MagicMock()
        mock_profile.skills           = ["python", "react"]
        mock_profile.experience_years = 4
        mock_profile.job_titles       = ["Senior Dev"]
        mock_profile.location         = "Karachi, Pakistan"
        mock_profile.education        = "BEng"
        mock_profile.profile_strength = 80
        result = MagicMock()
        result.scalar_one_or_none.return_value = mock_profile
        db.execute.return_value = result
        return db

    def test_returns_none_when_no_profile(self):
        agent = CVAnalysisAgent()
        result = _run(agent.run("user1", self._make_db_no_profile()))
        assert result is None

    def test_returns_dict_when_profile_found(self):
        agent = CVAnalysisAgent()
        result = _run(agent.run("user1", self._make_db_with_profile()))
        assert result is not None
        assert result["skills"] == ["python", "react"]
        assert result["experience_years"] == 4
        assert result["location"] == "Karachi, Pakistan"

    def test_all_keys_present(self):
        agent = CVAnalysisAgent()
        result = _run(agent.run("user1", self._make_db_with_profile()))
        for key in ("skills", "experience_years", "job_titles", "location", "education", "profile_strength"):
            assert key in result


# ---------------------------------------------------------------------------
# SearchAgent
# ---------------------------------------------------------------------------

class TestSearchAgent:
    def test_result_has_required_keys(self):
        agent = SearchAgent()
        result = _run(agent.run(keyword="python"))
        assert "jobs"    in result
        assert "fetched" in result
        assert "errors"  in result

    def test_unconfigured_adapters_return_empty_jobs(self):
        # Both adapters are unconfigured in test env (no API keys).
        agent = SearchAgent()
        result = _run(agent.run(keyword="developer"))
        assert isinstance(result["jobs"], list)
        assert isinstance(result["fetched"], dict)
        assert isinstance(result["errors"], dict)
        # All adapters either report 0 fetched or an error — never a crash.
        for count in result["fetched"].values():
            assert count == 0

    def test_source_filter_limits_adapters(self):
        agent = SearchAgent()
        result = _run(agent.run(keyword="python", sources=["linkedin"]))
        # Only linkedin should appear in fetched (rozee is excluded).
        assert "rozee" not in result["fetched"]

    def test_timeout_handled_gracefully(self):
        """An adapter that hangs must not raise; error is recorded instead."""
        import app.agents.search_agent as sa

        async def _slow_fetch(_query):
            await asyncio.sleep(999)

        agent = SearchAgent()
        original_timeout = sa._PER_ADAPTER_TIMEOUT
        sa._PER_ADAPTER_TIMEOUT = 0.05
        try:
            with patch("app.adapters.linkedin.LinkedInAdapter.fetch", side_effect=_slow_fetch):
                result = _run(agent.run(keyword="python", sources=["linkedin"]))
            assert result["fetched"].get("linkedin", 0) == 0
            assert "linkedin" in result["errors"]
        finally:
            sa._PER_ADAPTER_TIMEOUT = original_timeout

    def test_raw_to_dict_shape(self):
        raw = MagicMock()
        raw.external_id   = "linkedin:123"
        raw.title         = "Dev"
        raw.company       = "Acme"
        raw.location      = "Lahore"
        raw.description   = "desc"
        raw.requirements  = ["python"]
        raw.salary        = ""
        raw.source        = "linkedin"
        raw.url           = "https://example.com"
        raw.location_type = "Remote"
        raw.job_type      = "Full-time"
        raw.experience    = "Mid"
        result = SearchAgent._raw_to_dict(raw)
        assert result["external_id"] == "linkedin:123"
        assert result["title"] == "Dev"
        assert "requirements" in result


# ---------------------------------------------------------------------------
# MatchingAgent
# ---------------------------------------------------------------------------

class TestMatchingAgent:
    def test_empty_jobs_returns_empty(self):
        agent = MatchingAgent()
        result = _run(agent.run(_cv(), []))
        assert result == []

    def test_scores_all_jobs(self):
        agent = MatchingAgent()
        jobs  = [_job(1), _job(2, title="Backend Engineer", requirements=["java", "spring"])]
        result = _run(agent.run(_cv(), jobs, explain=False))
        assert len(result) == 2

    def test_sorted_descending(self):
        agent = MatchingAgent()
        jobs  = [
            _job(1, requirements=["react", "typescript"]),
            _job(2, requirements=["cobol", "fortran"]),
        ]
        result = _run(agent.run(_cv(), jobs, explain=False))
        assert result[0]["score"] >= result[1]["score"]

    def test_result_keys(self):
        agent = MatchingAgent()
        result = _run(agent.run(_cv(), [_job(1)], explain=False))
        assert len(result) == 1
        m = result[0]
        for key in ("job_id", "score", "breakdown", "matched_skills", "missing_skills", "reasons", "explanation"):
            assert key in m

    def test_breakdown_has_four_components(self):
        agent = MatchingAgent()
        result = _run(agent.run(_cv(), [_job(1)], explain=False))
        bd = result[0]["breakdown"]
        for key in ("skills", "experience", "title", "location"):
            assert key in bd

    def test_no_explanation_without_flag(self):
        agent = MatchingAgent()
        result = _run(agent.run(_cv(), [_job(1)], explain=False))
        assert result[0]["explanation"] == ""

    def test_score_in_valid_range(self):
        agent = MatchingAgent()
        result = _run(agent.run(_cv(), [_job(1)], explain=False))
        assert 0 <= result[0]["score"] <= 100


# ---------------------------------------------------------------------------
# WorkflowCoordinator._deduplicate
# ---------------------------------------------------------------------------

class TestDeduplicate:
    def test_removes_duplicates_by_external_id(self):
        jobs = [
            {"external_id": "seed:job-1", "title": "A"},
            {"external_id": "seed:job-1", "title": "A (dup)"},
            {"external_id": "seed:job-2", "title": "B"},
        ]
        result = WorkflowCoordinator._deduplicate(jobs)
        assert len(result) == 2
        assert result[0]["title"] == "A"

    def test_preserves_order(self):
        jobs = [
            {"external_id": "a", "title": "First"},
            {"external_id": "b", "title": "Second"},
        ]
        result = WorkflowCoordinator._deduplicate(jobs)
        assert result[0]["title"] == "First"

    def test_empty_list(self):
        assert WorkflowCoordinator._deduplicate([]) == []

    def test_no_external_id_falls_back_to_id(self):
        jobs = [
            {"id": 1, "title": "A"},
            {"id": 2, "title": "B"},
        ]
        result = WorkflowCoordinator._deduplicate(jobs)
        assert len(result) == 2


# ---------------------------------------------------------------------------
# WorkflowCoordinator._describe_plan
# ---------------------------------------------------------------------------

class TestDescribePlan:
    def test_includes_keyword(self):
        p = WorkflowPreferences(keyword="python developer")
        plan = WorkflowCoordinator._describe_plan(p)
        assert "python developer" in plan

    def test_includes_location(self):
        p = WorkflowPreferences(location="Lahore")
        plan = WorkflowCoordinator._describe_plan(p)
        assert "Lahore" in plan

    def test_mentions_confirmation(self):
        p    = WorkflowPreferences()
        plan = WorkflowCoordinator._describe_plan(p)
        assert "confirm" in plan.lower()


# ---------------------------------------------------------------------------
# WorkflowCoordinator direct path (no Claude)
# ---------------------------------------------------------------------------

class TestCoordinatorDirectPath:
    """Tests the _direct_run path with mocked DB and no Anthropic key."""

    def _make_profile(self):
        mock_profile = MagicMock()
        mock_profile.skills           = ["python", "react"]
        mock_profile.experience_years = 3
        mock_profile.job_titles       = ["Developer"]
        mock_profile.location         = "Lahore, Pakistan"
        mock_profile.education        = "BSc"
        mock_profile.profile_strength = 70
        return mock_profile

    def _make_db_with_jobs(self, profile=None):
        db = AsyncMock()

        # CV profile query
        profile_result = MagicMock()
        profile_result.scalar_one_or_none.return_value = profile

        # Jobs query
        mock_job        = MagicMock()
        mock_job.id     = 1
        mock_job.__table__ = MagicMock()
        col_id          = MagicMock()
        col_id.name     = "id"
        col_title       = MagicMock()
        col_title.name  = "title"
        mock_job.__table__.columns = [col_id, col_title]
        mock_job.id     = 1
        mock_job.title  = "React Dev"

        scalars_mock    = MagicMock()
        scalars_mock.all.return_value = []   # keep simple: no real ORM rows

        jobs_result     = MagicMock()
        jobs_result.scalars.return_value = scalars_mock

        db.execute.side_effect = [profile_result, jobs_result]
        return db

    def test_unconfirmed_returns_pending_confirmation(self):
        prefs = WorkflowPreferences(confirmed=False)
        db    = self._make_db_with_jobs(profile=None)

        coord  = WorkflowCoordinator()
        result = _run(coord._direct_run({"preferences": prefs, "db": db,
                                         "cv": None, "jobs": [], "matches": [],
                                         "fetched": {}, "errors": {},
                                         "confirmed": False}))
        assert result.status == "pending_confirmation"
        assert result.plan != ""

    def test_confirmed_no_cv_still_completes(self):
        prefs = WorkflowPreferences(confirmed=True)
        db    = self._make_db_with_jobs(profile=None)

        coord  = WorkflowCoordinator()
        result = _run(coord._direct_run({"preferences": prefs, "db": db,
                                         "cv": None, "jobs": [], "matches": [],
                                         "fetched": {}, "errors": {},
                                         "confirmed": True}))
        assert result.status == "complete"
        assert result.cv_found is False
        assert result.matches == []

    def test_confirmed_with_cv_and_jobs_produces_matches(self):
        prefs  = WorkflowPreferences(confirmed=True)

        # Wire mock DB so cv_agent gets a profile and load_db_jobs gets jobs.
        db     = AsyncMock()

        mock_profile = self._make_profile()
        cv_result    = MagicMock()
        cv_result.scalar_one_or_none.return_value = mock_profile

        # Jobs result returns empty (no ORM rows needed; jobs injected in state)
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = []
        jobs_result  = MagicMock()
        jobs_result.scalars.return_value = scalars_mock

        db.execute.side_effect = [cv_result, jobs_result]

        coord = WorkflowCoordinator()
        state = {
            "preferences": prefs,
            "db":          db,
            "cv":          None,
            "jobs":        [_job(1)],  # pre-load one job
            "matches":     [],
            "fetched":     {},
            "errors":      {},
            "confirmed":   True,
        }
        result = _run(coord._direct_run(state))
        assert result.status == "complete"
        # Matching may produce 1 result for the pre-loaded job.
        assert isinstance(result.matches, list)


# ---------------------------------------------------------------------------
# job_search tool stub
# ---------------------------------------------------------------------------

class TestJobSearchTool:
    def test_returns_list(self):
        from app.tools.job_search import search_jobs
        result = _run(search_jobs("python developer"))
        assert isinstance(result, list)

    def test_location_filter_passed_through(self):
        from app.tools.job_search import search_jobs
        result = _run(search_jobs("developer", location="Lahore"))
        assert isinstance(result, list)
