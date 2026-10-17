from pydantic import BaseModel


class ScoreBreakdownSchema(BaseModel):
    skills:     float
    experience: float
    title:      float
    location:   float
    total:      float


class JobMatchResponse(BaseModel):
    job_id:         int
    rank:           int
    score:          float
    breakdown:      ScoreBreakdownSchema
    matched_skills: list[str]
    missing_skills: list[str]
    reasons:        list[str]
    explanation:    str = ""


class MatchListResponse(BaseModel):
    matches: list[JobMatchResponse]
    total:   int
    weights: dict[str, float]
