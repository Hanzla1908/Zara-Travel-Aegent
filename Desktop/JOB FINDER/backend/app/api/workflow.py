"""
Workflow API — POST /api/workflow/run

Runs the multi-agent job-finding workflow.

Confirmation gate
-----------------
External API calls (LinkedIn, Rozee.pk) are made ONLY when the request body
includes ``confirmed: true``.  Without it the endpoint returns a plan and
any local DB matches so the caller can display a confirmation prompt before
re-submitting.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import WorkflowPreferences, WorkflowResult
from app.agents.coordinator import WorkflowCoordinator
from app.models.database import get_db

router = APIRouter()
_coordinator = WorkflowCoordinator()


@router.post("/run", response_model=WorkflowResult)
async def run_workflow(
    preferences: WorkflowPreferences,
    db: AsyncSession = Depends(get_db),
) -> WorkflowResult:
    """
    Execute the job-finding workflow.

    - Without ``confirmed=true``: returns ``status="pending_confirmation"``
      with a plain-English plan and any local-DB matches.
    - With ``confirmed=true``: runs external searches, matches against CV,
      and returns ranked results with optional Claude explanations.
    """
    return await _coordinator.run(preferences, db)
