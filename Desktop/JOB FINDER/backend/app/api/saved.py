from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.database import get_db
from app.models.job import Job
from app.models.saved_job import SavedJob
from app.schemas.job import JobResponse

router = APIRouter()


def _job_to_dict(job: Job) -> dict:
    return {c.name: getattr(job, c.name) for c in job.__table__.columns}


@router.get("/", response_model=list[JobResponse])
async def list_saved(
    user_id: str = Query(default="default"),
    db: AsyncSession = Depends(get_db),
):
    saved_result = await db.execute(
        select(SavedJob).where(SavedJob.user_id == user_id).order_by(SavedJob.saved_at.desc())
    )
    saved_rows = saved_result.scalars().all()

    if not saved_rows:
        return []

    job_ids = [s.job_id for s in saved_rows]
    jobs_result = await db.execute(select(Job).where(Job.id.in_(job_ids)))
    jobs_map = {j.id: j for j in jobs_result.scalars().all()}

    return [
        JobResponse(**_job_to_dict(jobs_map[s.job_id]), saved=True)
        for s in saved_rows
        if s.job_id in jobs_map
    ]


@router.post("/{job_id}", status_code=201)
async def save_job(
    job_id: int,
    user_id: str = Query(default="default"),
    db: AsyncSession = Depends(get_db),
):
    job_result = await db.execute(select(Job).where(Job.id == job_id))
    if not job_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Job not found")

    existing = await db.execute(
        select(SavedJob).where(SavedJob.job_id == job_id, SavedJob.user_id == user_id)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Job already saved")

    db.add(SavedJob(user_id=user_id, job_id=job_id))
    await db.commit()
    return {"message": "Job saved", "job_id": job_id}


@router.delete("/{job_id}", status_code=200)
async def unsave_job(
    job_id: int,
    user_id: str = Query(default="default"),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(SavedJob).where(SavedJob.job_id == job_id, SavedJob.user_id == user_id)
    )
    saved = result.scalar_one_or_none()
    if not saved:
        raise HTTPException(status_code=404, detail="Saved job not found")

    await db.delete(saved)
    await db.commit()
    return {"message": "Job unsaved", "job_id": job_id}


@router.patch("/{job_id}/notes", status_code=200)
async def update_notes(
    job_id: int,
    notes: str,
    user_id: str = Query(default="default"),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(SavedJob).where(SavedJob.job_id == job_id, SavedJob.user_id == user_id)
    )
    saved = result.scalar_one_or_none()
    if not saved:
        raise HTTPException(status_code=404, detail="Saved job not found")

    saved.notes = notes
    await db.commit()
    return {"message": "Notes updated"}
