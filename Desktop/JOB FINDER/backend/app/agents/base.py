"""
Shared types for the multi-agent job-finding workflow.
"""

from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, Field


class WorkflowPreferences(BaseModel):
    """Validated input for the workflow coordinator."""
    keyword:    str        = ""
    location:   str        = ""
    experience: list[str]  = []
    job_type:   str        = ""
    sources:    list[str]  = []
    limit:      int        = Field(default=20, ge=1, le=100)
    explain:    bool       = False
    user_id:    str        = "default"
    # User must explicitly set confirmed=True to allow external API calls.
    confirmed:  bool       = False


class MatchSummary(BaseModel):
    """Per-job match result returned by the workflow."""
    job_id:         int
    score:          float
    breakdown:      dict[str, float]
    matched_skills: list[str]
    missing_skills: list[str]
    reasons:        list[str]
    explanation:    str = ""


class WorkflowResult(BaseModel):
    """Validated output of the workflow coordinator."""
    status:               Literal["complete", "pending_confirmation", "error"]
    matches:              list[MatchSummary]   = []
    sources_fetched:      dict[str, int]       = {}
    total_jobs_searched:  int                  = 0
    errors:               dict[str, str]       = {}
    # Shown to the user when status="pending_confirmation".
    plan:                 str                  = ""
    cv_found:             bool                 = False
    # Claude-generated prose summary (populated when Claude is available).
    summary:              str                  = ""
