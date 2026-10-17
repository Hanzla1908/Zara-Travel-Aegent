from datetime import datetime
from pydantic import BaseModel, Field


class JobBase(BaseModel):
    title: str
    company: str
    initials: str = ""
    color: str = "#4F46E5"
    location: str = ""
    location_type: str = "On-site"
    type: str = "Full-time"
    experience: str = "Mid"
    salary: str = ""
    match_score: float = Field(ge=0, le=100, default=0.0)
    source: str = "linkedin"
    posted_days: int = Field(ge=0, default=0)


class JobCreate(JobBase):
    description: str = ""
    requirements: list[str] = []
    matching_skills: list[str] = []
    missing_skills: list[str] = []
    tags: list[str] = []
    external_id: str = ""
    url: str = ""


class JobResponse(JobCreate):
    id: int
    created_at: datetime
    saved: bool = False

    model_config = {"from_attributes": True}


class JobListResponse(BaseModel):
    jobs: list[JobResponse]
    total: int
    page: int
    page_size: int
