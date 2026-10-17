from datetime import datetime
from pydantic import BaseModel, Field


class CVProfileResponse(BaseModel):
    id: int
    user_id: str
    file_name: str
    file_size: int
    skills: list[str]
    experience_years: int
    education: str
    job_titles: list[str]
    location: str
    profile_strength: int
    uploaded_at: datetime

    model_config = {"from_attributes": True}


class ClaudeExtractedProfile(BaseModel):
    """Validated shape of the JSON Claude returns."""
    skills: list[str] = Field(default_factory=list)
    experience_years: int = Field(default=0, ge=0, le=60)
    education: str = Field(default="")
    job_titles: list[str] = Field(default_factory=list)
    location: str = Field(default="")
