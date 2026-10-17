"""
Unit tests for the deterministic job-match scoring service.

All tests are pure — no database, no network, no Claude calls.
The async rank_jobs function is tested with explain=False only.
"""

import asyncio
import pytest

from app.services.matcher import (
    DEFAULT_WEIGHTS,
    MatchWeights,
    ScoreBreakdown,
    build_reasons,
    calculate_match,
    rank_jobs,
    score_experience,
    score_location,
    score_skills,
    score_title,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _cv(**kw) -> dict:
    return {
        "skills": ["react", "typescript", "python", "git"],
        "experience_years": 3,
        "job_titles": ["Frontend Developer", "React Developer"],
        "location": "Lahore, Pakistan",
        **kw,
    }


def _job(**kw) -> dict:
    return {
        "id": 1,
        "title": "Frontend Developer",
        "requirements": ["react", "typescript", "css"],
        "description": "",
        "experience": "Mid",
        "location": "Lahore, Pakistan",
        "location_type": "On-site",
        **kw,
    }


# ---------------------------------------------------------------------------
# MatchWeights
# ---------------------------------------------------------------------------

class TestMatchWeights:
    def test_defaults_sum_to_one(self):
        w = MatchWeights()
        assert abs(w.skills + w.experience + w.title + w.location - 1.0) < 0.001

    def test_custom_valid(self):
        w = MatchWeights(skills=0.6, experience=0.2, title=0.1, location=0.1)
        assert w.skills == 0.6

    def test_invalid_raises_value_error(self):
        with pytest.raises(ValueError, match="sum to 1.0"):
            MatchWeights(skills=0.5, experience=0.5, title=0.1, location=0.1)

    def test_tiny_float_rounding_accepted(self):
        # Normalised weights may have tiny float errors; must not raise.
        w = MatchWeights(
            skills=round(0.5 / 1.0, 6),
            experience=round(0.25 / 1.0, 6),
            title=round(0.15 / 1.0, 6),
            location=round(0.10 / 1.0, 6),
        )
        assert w is not None


# ---------------------------------------------------------------------------
# score_skills
# ---------------------------------------------------------------------------

class TestScoreSkills:
    def test_perfect_match(self):
        score, matched, missing = score_skills(["python", "react"], ["python", "react"])
        assert score == 100.0
        assert set(matched) == {"python", "react"}
        assert missing == []

    def test_no_match(self):
        score, matched, missing = score_skills(["java"], ["python", "react"])
        assert score == 0.0
        assert matched == []
        assert len(missing) == 2

    def test_partial_match(self):
        score, matched, missing = score_skills(["python"], ["python", "react", "typescript"])
        assert 0 < score < 100
        assert len(matched) >= 1
        assert len(missing) >= 1

    def test_no_requirements_returns_neutral(self):
        score, matched, missing = score_skills(["python"], [], "")
        assert score == 50.0
        assert matched == []
        assert missing == []

    def test_empty_requirements_and_description(self):
        score, matched, missing = score_skills([], [], "")
        assert score == 50.0

    def test_case_insensitive(self):
        score, _, _ = score_skills(["Python", "React"], ["python", "react"])
        assert score == 100.0

    def test_skills_from_description(self):
        score, matched, missing = score_skills(["python"], [], "We use python and docker")
        # "python" should match something extracted from description
        assert len(matched) >= 1

    def test_stop_words_not_counted_as_skills(self):
        _, matched, _ = score_skills(["and", "or", "the"], ["python", "react"])
        # Stop words in cv_skills should not appear as matched skills
        assert "and" not in matched
        assert "or" not in matched


# ---------------------------------------------------------------------------
# score_experience
# ---------------------------------------------------------------------------

class TestScoreExperience:
    def test_in_range_returns_100(self):
        assert score_experience(3, "Mid") == 100.0

    def test_at_lower_bound_returns_100(self):
        assert score_experience(2, "Mid") == 100.0

    def test_at_upper_bound_returns_100(self):
        assert score_experience(5, "Mid") == 100.0

    def test_below_range_is_penalised(self):
        score = score_experience(0, "Senior")
        assert 0.0 <= score < 80.0

    def test_overqualified_returns_80(self):
        assert score_experience(10, "Junior") == 80.0
        assert score_experience(15, "Mid") == 80.0

    def test_junior_zero_years_returns_100(self):
        # Junior range is (0, 2); 0 is inside it
        assert score_experience(0, "Junior") == 100.0

    def test_unknown_level_defaults_to_mid(self):
        # 3 years is inside Mid range (2-5)
        assert score_experience(3, "UnknownLevel") == 100.0

    def test_lead_range(self):
        assert score_experience(10, "Lead") == 100.0

    def test_below_lead_range(self):
        score = score_experience(2, "Lead")
        assert 0 <= score < 80.0


# ---------------------------------------------------------------------------
# score_title
# ---------------------------------------------------------------------------

class TestScoreTitle:
    def test_exact_match(self):
        assert score_title(["React Developer"], "React Developer") == 100.0

    def test_partial_overlap(self):
        score = score_title(["Senior React Engineer"], "React Developer")
        assert 0 < score < 100

    def test_no_overlap(self):
        score = score_title(["Java Backend Engineer"], "React Developer")
        assert score < 30

    def test_no_cv_titles_returns_30(self):
        assert score_title([], "React Developer") == 30.0

    def test_multiple_titles_best_used(self):
        # Second title is a perfect match
        score = score_title(["Java Developer", "React Developer"], "React Developer")
        assert score == 100.0

    def test_case_insensitive(self):
        score = score_title(["react developer"], "React Developer")
        assert score == 100.0

    def test_empty_job_title_returns_50(self):
        score = score_title(["React Developer"], "")
        assert score == 50.0


# ---------------------------------------------------------------------------
# score_location
# ---------------------------------------------------------------------------

class TestScoreLocation:
    def test_remote_returns_100(self):
        assert score_location("Lahore, Pakistan", "New York, USA", "Remote") == 100.0

    def test_hybrid_returns_70(self):
        assert score_location("Lahore, Pakistan", "Lahore, Pakistan", "Hybrid") == 70.0

    def test_same_city_onsite_returns_100(self):
        assert score_location("Lahore, Pakistan", "Lahore, Pakistan", "On-site") == 100.0

    def test_same_country_returns_60(self):
        assert score_location("Karachi, Pakistan", "Lahore, Pakistan", "On-site") == 60.0

    def test_different_region_returns_20(self):
        assert score_location("Lahore, Pakistan", "London, UK", "On-site") == 20.0

    def test_no_cv_location_returns_50(self):
        assert score_location("", "Lahore, Pakistan", "On-site") == 50.0

    def test_no_job_location_returns_50(self):
        assert score_location("Lahore, Pakistan", "", "On-site") == 50.0

    def test_both_empty_returns_50(self):
        assert score_location("", "", "On-site") == 50.0

    def test_case_insensitive_city(self):
        assert score_location("lahore, pakistan", "Lahore, Pakistan", "On-site") == 100.0


# ---------------------------------------------------------------------------
# build_reasons
# ---------------------------------------------------------------------------

class TestBuildReasons:
    def _breakdown(self, **kw) -> ScoreBreakdown:
        return ScoreBreakdown(
            skills=kw.get("skills", 80.0),
            experience=kw.get("experience", 100.0),
            title=kw.get("title", 80.0),
            location=kw.get("location", 100.0),
            total=kw.get("total", 88.0),
        )

    def test_reasons_is_list(self):
        bd = self._breakdown()
        reasons = build_reasons(bd, ["react"], ["vue"], 3, "Mid")
        assert isinstance(reasons, list)
        assert len(reasons) >= 1

    def test_includes_matched_skills(self):
        bd = self._breakdown()
        reasons = build_reasons(bd, ["react", "typescript"], [], 3, "Mid")
        combined = " ".join(reasons)
        assert "react" in combined.lower() or "typescript" in combined.lower()

    def test_includes_missing_skills(self):
        bd = self._breakdown()
        reasons = build_reasons(bd, [], ["vue", "graphql"], 3, "Mid")
        combined = " ".join(reasons)
        assert "vue" in combined.lower() or "missing" in combined.lower()

    def test_experience_gap_mentioned(self):
        bd = self._breakdown(experience=30.0)
        reasons = build_reasons(bd, [], [], 1, "Senior")
        combined = " ".join(reasons)
        assert "gap" in combined.lower() or "short" in combined.lower()

    def test_overqualified_mentioned(self):
        bd = self._breakdown(experience=80.0)
        reasons = build_reasons(bd, [], [], 10, "Junior")
        combined = " ".join(reasons)
        assert "overqualified" in combined.lower()

    def test_remote_location_mentioned(self):
        bd = self._breakdown(location=100.0)
        reasons = build_reasons(bd, [], [], 3, "Mid")
        combined = " ".join(reasons)
        assert "remote" in combined.lower() or "no commute" in combined.lower()


# ---------------------------------------------------------------------------
# calculate_match (integration of all components)
# ---------------------------------------------------------------------------

class TestCalculateMatch:
    def test_score_in_valid_range(self):
        result = calculate_match(_cv(), _job())
        assert 0 <= result.score <= 100

    def test_good_match_scores_high(self):
        result = calculate_match(_cv(), _job())
        assert result.score >= 70.0

    def test_matched_skills_populated(self):
        result = calculate_match(_cv(), _job())
        assert len(result.matched_skills) > 0

    def test_reasons_not_empty(self):
        result = calculate_match(_cv(), _job())
        assert len(result.reasons) >= 1

    def test_job_id_preserved(self):
        result = calculate_match(_cv(), _job(id=42))
        assert result.job_id == 42

    def test_missing_cv_data_does_not_crash(self):
        result = calculate_match({}, _job())
        assert 0 <= result.score <= 100

    def test_missing_job_data_does_not_crash(self):
        result = calculate_match(_cv(), {"id": 99})
        assert 0 <= result.score <= 100

    def test_empty_both_does_not_crash(self):
        result = calculate_match({}, {})
        assert 0 <= result.score <= 100

    def test_custom_weights_affect_score(self):
        # With no skills, skills-heavy weighting should score worse
        w_skills = MatchWeights(skills=0.8, experience=0.1, title=0.05, location=0.05)
        w_exp    = MatchWeights(skills=0.2, experience=0.6, title=0.1, location=0.1)
        r_skills = calculate_match(_cv(skills=[]), _job(), w_skills)
        r_exp    = calculate_match(_cv(skills=[]), _job(), w_exp)
        assert r_skills.score <= r_exp.score

    def test_remote_job_improves_location_score(self):
        r_onsite = calculate_match(_cv(location="Karachi"), _job(location="London", location_type="On-site"))
        r_remote = calculate_match(_cv(location="Karachi"), _job(location="London", location_type="Remote"))
        assert r_remote.score > r_onsite.score

    def test_score_worse_without_required_skills(self):
        r_with    = calculate_match(_cv(skills=["react", "typescript"]), _job())
        r_without = calculate_match(_cv(skills=[]), _job())
        assert r_with.score > r_without.score

    def test_explanation_starts_empty(self):
        result = calculate_match(_cv(), _job())
        assert result.explanation == ""


# ---------------------------------------------------------------------------
# rank_jobs (async, explain=False — no Claude calls)
# ---------------------------------------------------------------------------

class TestRankJobs:
    def _run(self, coro):
        return asyncio.run(coro)

    def test_sorted_descending(self):
        jobs = [
            _job(id=1, requirements=["react", "typescript", "python"]),
            _job(id=2, requirements=["cobol", "fortran", "assembly"]),
        ]
        results = self._run(rank_jobs(_cv(), jobs, explain=False))
        assert results[0].score >= results[1].score

    def test_returns_all_jobs(self):
        jobs = [_job(id=i) for i in range(5)]
        results = self._run(rank_jobs(_cv(), jobs, explain=False))
        assert len(results) == 5

    def test_empty_jobs_list(self):
        results = self._run(rank_jobs(_cv(), [], explain=False))
        assert results == []

    def test_no_explanation_without_flag(self):
        jobs = [_job(id=1)]
        results = self._run(rank_jobs(_cv(), jobs, explain=False))
        assert results[0].explanation == ""

    def test_custom_weights_respected(self):
        w = MatchWeights(skills=0.7, experience=0.1, title=0.1, location=0.1)
        jobs = [_job(id=1)]
        results = self._run(rank_jobs(_cv(), jobs, weights=w, explain=False))
        assert len(results) == 1
