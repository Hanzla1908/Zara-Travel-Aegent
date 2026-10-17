import io
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from app.models.database import get_db
from app.models.cv_profile import CVProfile
from app.models.job import Job
from app.schemas.cv import CVProfileResponse
from app.schemas.match import MatchListResponse, JobMatchResponse, ScoreBreakdownSchema
from app.services.cv_parser import parse_cv
from app.services.matcher import MatchWeights, rank_jobs

router = APIRouter()


@router.post("/upload", response_model=CVProfileResponse, status_code=201)
async def upload_cv(
    file: UploadFile = File(...),
    user_id: str = Query(default="default"),
    db: AsyncSession = Depends(get_db),
):
    allowed = {"application/pdf", "application/msword",
               "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}
    if file.content_type not in allowed:
        raise HTTPException(status_code=415, detail="Unsupported file type. Upload PDF or DOCX.")

    contents = await file.read()
    if len(contents) > 10 * 1024 * 1024:  # 10 MB limit
        raise HTTPException(status_code=413, detail="File too large. Max size is 10 MB.")

    parsed = await parse_cv(contents, file.content_type or "")

    # Replace existing profile for this user
    await db.execute(delete(CVProfile).where(CVProfile.user_id == user_id))

    profile = CVProfile(
        user_id=user_id,
        file_name=file.filename or "resume",
        file_size=len(contents),
        raw_text=parsed.get("raw_text", ""),
        skills=parsed.get("skills", []),
        experience_years=parsed.get("experience_years", 0),
        education=parsed.get("education", ""),
        job_titles=parsed.get("job_titles", []),
        location=parsed.get("location", ""),
        profile_strength=parsed.get("profile_strength", 50),
    )
    db.add(profile)
    await db.commit()
    await db.refresh(profile)
    return profile


@router.get("/profile", response_model=CVProfileResponse)
async def get_profile(
    user_id: str = Query(default="default"),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(CVProfile)
        .where(CVProfile.user_id == user_id)
        .order_by(CVProfile.uploaded_at.desc())
        .limit(1)
    )
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail="No CV uploaded yet")
    return profile


@router.get("/matches", response_model=MatchListResponse)
async def get_matches(
    user_id: str = Query(default="default"),
    explain: bool = Query(
        default=False,
        description="Generate Claude explanations for each match (uses API tokens).",
    ),
    skills_weight:     float = Query(default=0.50, ge=0.0, le=1.0),
    experience_weight: float = Query(default=0.25, ge=0.0, le=1.0),
    title_weight:      float = Query(default=0.15, ge=0.0, le=1.0),
    location_weight:   float = Query(default=0.10, ge=0.0, le=1.0),
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """
    Score and rank all jobs against the user's CV profile.

    Weights are normalised automatically so they always sum to 1.0.
    Passing explain=true calls Claude for each job's explanation.
    """
    cv_result = await db.execute(
        select(CVProfile)
        .where(CVProfile.user_id == user_id)
        .order_by(CVProfile.uploaded_at.desc())
        .limit(1)
    )
    profile = cv_result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail="No CV uploaded yet. Upload a CV first.")

    total_w = skills_weight + experience_weight + title_weight + location_weight
    if total_w <= 0:
        raise HTTPException(status_code=422, detail="At least one weight must be positive.")
    weights = MatchWeights(
        skills=round(skills_weight / total_w, 6),
        experience=round(experience_weight / total_w, 6),
        title=round(title_weight / total_w, 6),
        location=round(location_weight / total_w, 6),
    )

    jobs_result = await db.execute(select(Job))
    jobs = jobs_result.scalars().all()
    job_dicts = [
        {c.name: getattr(j, c.name) for c in j.__table__.columns}
        for j in jobs
    ]

    cv_dict = {
        "skills":           profile.skills or [],
        "experience_years": profile.experience_years or 0,
        "job_titles":       profile.job_titles or [],
        "location":         profile.location or "",
    }

    ranked = await rank_jobs(cv_dict, job_dicts, weights, explain=explain)
    total  = len(ranked)
    ranked = ranked[:limit]

    return MatchListResponse(
        matches=[
            JobMatchResponse(
                job_id=r.job_id,
                rank=i + 1,
                score=r.score,
                breakdown=ScoreBreakdownSchema(
                    skills=r.breakdown.skills,
                    experience=r.breakdown.experience,
                    title=r.breakdown.title,
                    location=r.breakdown.location,
                    total=r.breakdown.total,
                ),
                matched_skills=r.matched_skills,
                missing_skills=r.missing_skills,
                reasons=r.reasons,
                explanation=r.explanation,
            )
            for i, r in enumerate(ranked)
        ],
        total=total,
        weights={
            "skills":     weights.skills,
            "experience": weights.experience,
            "title":      weights.title,
            "location":   weights.location,
        },
    )


@router.delete("/profile", status_code=204)
async def delete_profile(
    user_id: str = Query(default="default"),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(CVProfile).where(CVProfile.user_id == user_id)
    )
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail="No CV profile found")
    await db.delete(profile)
    await db.commit()
