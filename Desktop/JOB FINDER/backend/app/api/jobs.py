from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, func

from app.models.database import get_db
from app.models.job import Job
from app.models.saved_job import SavedJob
from app.schemas.job import JobCreate, JobResponse, JobListResponse
from app.services.seeder import seed_jobs

router = APIRouter()


def _job_to_dict(job: Job) -> dict:
    return {c.name: getattr(job, c.name) for c in job.__table__.columns}


@router.get("/", response_model=JobListResponse)
async def list_jobs(
    keyword: str | None = Query(default=None),
    location: str | None = Query(default=None),
    experience: list[str] = Query(default=[]),
    type: str | None = Query(default=None),
    source: list[str] = Query(default=[]),
    sort: str = Query(default="match", pattern="^(match|date|salary)$"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    user_id: str = Query(default="default"),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Job)

    if keyword:
        kw = f"%{keyword}%"
        stmt = stmt.where(
            or_(
                Job.title.ilike(kw),
                Job.company.ilike(kw),
                Job.description.ilike(kw),
            )
        )
    if location:
        loc = f"%{location}%"
        stmt = stmt.where(
            or_(Job.location.ilike(loc), Job.location_type.ilike(loc))
        )
    if experience:
        stmt = stmt.where(Job.experience.in_(experience))
    if type:
        stmt = stmt.where(Job.type == type)
    if source:
        stmt = stmt.where(Job.source.in_(source))

    if sort == "match":
        stmt = stmt.order_by(Job.match_score.desc())
    elif sort == "date":
        stmt = stmt.order_by(Job.posted_days.asc())
    elif sort == "salary":
        stmt = stmt.order_by(Job.salary.desc())

    result = await db.execute(stmt)
    all_jobs = result.scalars().all()
    total = len(all_jobs)

    offset = (page - 1) * page_size
    page_jobs = all_jobs[offset : offset + page_size]

    saved_result = await db.execute(
        select(SavedJob.job_id).where(SavedJob.user_id == user_id)
    )
    saved_ids = {row[0] for row in saved_result}

    jobs = [
        JobResponse(**_job_to_dict(j), saved=(j.id in saved_ids))
        for j in page_jobs
    ]
    return JobListResponse(jobs=jobs, total=total, page=page, page_size=page_size)


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(
    job_id: int,
    user_id: str = Query(default="default"),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    saved_result = await db.execute(
        select(SavedJob).where(SavedJob.job_id == job_id, SavedJob.user_id == user_id)
    )
    saved = saved_result.scalar_one_or_none() is not None
    return JobResponse(**_job_to_dict(job), saved=saved)


@router.post("/seed", status_code=201)
async def seed(db: AsyncSession = Depends(get_db)):
    count = await seed_jobs(db)
    return {"seeded": count, "message": f"Seeded {count} jobs" if count else "Database already populated"}


class RefreshRequest(BaseModel):
    keyword: str = ""
    location: str = ""
    sources: list[str] = []
    experience: list[str] = []
    job_type: str = ""
    limit: int = 50


@router.post("/refresh", status_code=200)
async def refresh_jobs(body: RefreshRequest, db: AsyncSession = Depends(get_db)):
    """
    Fetch jobs from configured external adapters (LinkedIn, Rozee.pk),
    deduplicate against the database, and save new listings.

    Returns per-source fetch counts, the number of new jobs saved,
    the number of duplicates skipped, and any adapter error messages.
    Adapters that are not configured (missing API credentials) appear
    in the `errors` dict with an explanatory message — this is not a
    server error.
    """
    from app.adapters.base import AdapterQuery
    from app.adapters.registry import run_adapters

    query = AdapterQuery(
        keyword=body.keyword,
        location=body.location,
        experience=body.experience,
        job_type=body.job_type,
        limit=body.limit,
    )
    result = await run_adapters(db, query, sources=body.sources or None)
    return result
