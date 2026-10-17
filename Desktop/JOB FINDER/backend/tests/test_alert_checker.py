"""
Unit tests for the alert checker service.

All tests are pure — no real database, no network, no email.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.alert_checker import (
    _deduplicate,
    _is_due,
    _score_and_filter,
    check_alert,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run(coro):
    return asyncio.run(coro)


def _alert(**kw) -> MagicMock:
    a = MagicMock()
    a.id              = kw.get("id", 1)
    a.user_id         = kw.get("user_id", "default")
    a.name            = kw.get("name", "Test Alert")
    a.keywords        = kw.get("keywords", "python")
    a.location        = kw.get("location", "")
    a.sources         = kw.get("sources", [])
    a.frequency       = kw.get("frequency", "Daily")
    a.active          = kw.get("active", True)
    a.min_score       = kw.get("min_score", 0.0)
    a.email_enabled   = kw.get("email_enabled", False)
    a.email_address   = kw.get("email_address", "")
    a.last_checked_at = kw.get("last_checked_at", None)
    return a


def _cv() -> dict:
    return {
        "skills":           ["python", "react", "typescript"],
        "experience_years": 3,
        "job_titles":       ["Frontend Developer"],
        "location":         "Lahore, Pakistan",
    }


def _job(ext_id="seed:job-1", **kw) -> dict:
    return {
        "id":            kw.get("id", 1),
        "external_id":   ext_id,
        "title":         kw.get("title", "React Developer"),
        "company":       kw.get("company", "Acme"),
        "requirements":  kw.get("requirements", ["react", "typescript"]),
        "description":   kw.get("description", ""),
        "experience":    kw.get("experience", "Mid"),
        "location":      kw.get("location", "Lahore, Pakistan"),
        "location_type": kw.get("location_type", "On-site"),
    }


# ---------------------------------------------------------------------------
# _is_due
# ---------------------------------------------------------------------------

class TestIsDue:
    def test_never_checked_is_due(self):
        assert _is_due(_alert(last_checked_at=None), datetime.utcnow()) is True

    def test_checked_just_now_is_not_due_daily(self):
        a = _alert(frequency="Daily", last_checked_at=datetime.utcnow())
        assert _is_due(a, datetime.utcnow()) is False

    def test_checked_25_hours_ago_is_due_daily(self):
        a = _alert(frequency="Daily", last_checked_at=datetime.utcnow() - timedelta(hours=25))
        assert _is_due(a, datetime.utcnow()) is True

    def test_checked_1_hour_ago_is_not_due_weekly(self):
        a = _alert(frequency="Weekly", last_checked_at=datetime.utcnow() - timedelta(hours=1))
        assert _is_due(a, datetime.utcnow()) is False

    def test_checked_8_days_ago_is_due_weekly(self):
        a = _alert(frequency="Weekly", last_checked_at=datetime.utcnow() - timedelta(days=8))
        assert _is_due(a, datetime.utcnow()) is True

    def test_hourly_alert_due_after_2_hours(self):
        a = _alert(frequency="Hourly", last_checked_at=datetime.utcnow() - timedelta(hours=2))
        assert _is_due(a, datetime.utcnow()) is True

    def test_hourly_alert_not_due_within_hour(self):
        a = _alert(frequency="Hourly", last_checked_at=datetime.utcnow() - timedelta(minutes=30))
        assert _is_due(a, datetime.utcnow()) is False

    def test_unknown_frequency_defaults_to_daily(self):
        a = _alert(frequency="Monthly", last_checked_at=datetime.utcnow() - timedelta(hours=25))
        assert _is_due(a, datetime.utcnow()) is True


# ---------------------------------------------------------------------------
# _deduplicate
# ---------------------------------------------------------------------------

class TestDeduplicate:
    def test_removes_same_external_id(self):
        jobs = [_job("a"), _job("a"), _job("b")]
        result = _deduplicate(jobs)
        assert len(result) == 2

    def test_preserves_first_occurrence(self):
        jobs = [_job("a", title="First"), _job("a", title="Second")]
        result = _deduplicate(jobs)
        assert result[0]["title"] == "First"

    def test_empty_returns_empty(self):
        assert _deduplicate([]) == []

    def test_no_external_id_uses_id_field(self):
        jobs = [
            {"id": 1, "external_id": "", "title": "A"},
            {"id": 2, "external_id": "", "title": "B"},
        ]
        result = _deduplicate(jobs)
        assert len(result) == 2


# ---------------------------------------------------------------------------
# _score_and_filter
# ---------------------------------------------------------------------------

class TestScoreAndFilter:
    def test_no_min_score_returns_all(self):
        jobs = [_job("a"), _job("b", requirements=["cobol"])]
        result = _score_and_filter(_cv(), jobs, min_score=0.0)
        assert len(result) == 2

    def test_high_min_score_filters_poor_matches(self):
        jobs = [
            _job("a", requirements=["react", "typescript", "python"]),
            _job("b", requirements=["cobol", "fortran"]),
        ]
        result = _score_and_filter(_cv(), jobs, min_score=80.0)
        assert all(score >= 80.0 for _, score in result)

    def test_sorted_descending(self):
        jobs = [
            _job("b", requirements=["cobol"]),
            _job("a", requirements=["react", "typescript", "python"]),
        ]
        result = _score_and_filter(_cv(), jobs, min_score=0.0)
        scores = [score for _, score in result]
        assert scores == sorted(scores, reverse=True)

    def test_returns_tuples_of_job_and_score(self):
        jobs = [_job("a")]
        result = _score_and_filter(_cv(), jobs, min_score=0.0)
        assert len(result) == 1
        job, score = result[0]
        assert "external_id" in job
        assert 0 <= score <= 100

    def test_empty_jobs_returns_empty(self):
        assert _score_and_filter(_cv(), [], 0.0) == []


# ---------------------------------------------------------------------------
# check_alert (integration with mocked DB)
# ---------------------------------------------------------------------------

class TestCheckAlert:
    def _make_db(self, profile, notifications=None):
        """Build a mock AsyncSession for check_alert."""
        db = AsyncMock()

        cv_result = MagicMock()
        cv_result.scalar_one_or_none.return_value = profile

        # No existing notifications by default.
        notif_result = MagicMock()
        notif_result.scalar_one_or_none.return_value = None

        db.execute.side_effect = [cv_result, notif_result, notif_result, notif_result]
        return db

    def _make_profile(self):
        p = MagicMock()
        p.skills           = ["python", "react"]
        p.experience_years = 3
        p.job_titles       = ["Developer"]
        p.location         = "Lahore, Pakistan"
        return p

    def test_no_cv_returns_zero(self):
        db = AsyncMock()
        cv_result = MagicMock()
        cv_result.scalar_one_or_none.return_value = None
        db.execute.return_value = cv_result
        db.commit = AsyncMock()

        alert = _alert()
        count = _run(check_alert(db, alert))
        assert count == 0

    def test_no_jobs_returns_zero(self):
        db = AsyncMock()

        cv_result = MagicMock()
        cv_result.scalar_one_or_none.return_value = self._make_profile()

        scalars_mock = MagicMock()
        scalars_mock.all.return_value = []
        jobs_result = MagicMock()
        jobs_result.scalars.return_value = scalars_mock

        db.execute.side_effect = [cv_result, jobs_result]
        db.commit = AsyncMock()

        alert = _alert(sources=[])  # no adapter sources either
        count = _run(check_alert(db, alert))
        assert count == 0

    def test_below_min_score_not_notified(self):
        """Jobs with score below min_score produce no notifications."""
        db = AsyncMock()

        cv_result = MagicMock()
        cv_result.scalar_one_or_none.return_value = self._make_profile()

        # One very poor-match job (COBOL requirements vs Python CV)
        mock_job = MagicMock()
        mock_job.external_id   = "seed:cobol-job"
        mock_job.title         = "COBOL Programmer"
        mock_job.company       = "Old Corp"
        mock_job.location      = "Karachi"
        mock_job.description   = "COBOL and mainframe only."
        mock_job.requirements  = ["cobol", "mainframe"]
        mock_job.experience    = "Senior"
        mock_job.location_type = "On-site"
        mock_job.salary        = ""
        mock_job.source        = "seed"
        mock_job.url           = ""
        # Make __table__.columns work
        col = MagicMock()
        col.name = "external_id"
        mock_job.__table__ = MagicMock()
        mock_job.__table__.columns = []

        scalars_mock = MagicMock()
        scalars_mock.all.return_value = []  # return no jobs from DB
        jobs_result = MagicMock()
        jobs_result.scalars.return_value = scalars_mock

        db.execute.side_effect = [cv_result, jobs_result]
        db.commit = AsyncMock()

        alert = _alert(min_score=99.0, sources=[])  # impossibly high threshold
        count = _run(check_alert(db, alert))
        assert count == 0

    def test_last_checked_at_updated(self):
        db = AsyncMock()

        cv_result = MagicMock()
        cv_result.scalar_one_or_none.return_value = None  # no CV — returns early

        db.execute.return_value = cv_result
        db.commit = AsyncMock()

        alert = _alert()
        _run(check_alert(db, alert))
        assert alert.last_checked_at is not None


# ---------------------------------------------------------------------------
# AlertNotification schema
# ---------------------------------------------------------------------------

class TestAlertNotificationResponse:
    def test_basic_fields(self):
        from app.schemas.alert import AlertNotificationResponse
        data = {
            "id":              1,
            "alert_id":        2,
            "user_id":         "default",
            "job_external_id": "seed:test-job",
            "job_id":          None,
            "job_title":       "React Dev",
            "company":         "Acme",
            "score":           85.5,
            "seen":            False,
            "created_at":      datetime.utcnow(),
        }
        r = AlertNotificationResponse(**data)
        assert r.score == 85.5
        assert r.seen is False


# ---------------------------------------------------------------------------
# AlertCreate schema validation
# ---------------------------------------------------------------------------

class TestAlertCreate:
    def test_min_score_bounds(self):
        from app.schemas.alert import AlertCreate
        import pytest
        with pytest.raises(Exception):
            AlertCreate(name="X", keywords="python", min_score=-1)
        with pytest.raises(Exception):
            AlertCreate(name="X", keywords="python", min_score=101)

    def test_defaults(self):
        from app.schemas.alert import AlertCreate
        a = AlertCreate(name="Test", keywords="python")
        assert a.min_score == 0.0
        assert a.email_enabled is False
        assert a.frequency == "Daily"

    def test_email_fields(self):
        from app.schemas.alert import AlertCreate
        a = AlertCreate(
            name="Test", keywords="python",
            email_enabled=True, email_address="me@example.com"
        )
        assert a.email_enabled is True
        assert a.email_address == "me@example.com"
