from datetime import datetime
from pydantic import BaseModel, Field, EmailStr


class AlertCreate(BaseModel):
    name:          str        = Field(min_length=1, max_length=255)
    keywords:      str        = Field(min_length=1, max_length=500)
    location:      str        = ""
    frequency:     str        = "Daily"
    sources:       list[str]  = ["linkedin", "rozee"]
    min_score:     float      = Field(default=0.0, ge=0.0, le=100.0,
                                      description="Minimum match score (0–100) to trigger a notification.")
    email_enabled: bool       = Field(default=False,
                                      description="Send email on new matches. Requires SMTP configured in .env.")
    email_address: str        = Field(default="",
                                      description="Destination address when email_enabled=true.")


class AlertUpdate(BaseModel):
    name:          str | None        = None
    keywords:      str | None        = None
    location:      str | None        = None
    frequency:     str | None        = None
    sources:       list[str] | None  = None
    active:        bool | None       = None
    min_score:     float | None      = Field(default=None, ge=0.0, le=100.0)
    email_enabled: bool | None       = None
    email_address: str | None        = None


class AlertResponse(BaseModel):
    id:              int
    user_id:         str
    name:            str
    keywords:        str
    location:        str
    frequency:       str
    sources:         list[str]
    active:          bool
    min_score:       float
    email_enabled:   bool
    email_address:   str
    last_checked_at: datetime | None = None
    created_at:      datetime

    model_config = {"from_attributes": True}


class AlertNotificationResponse(BaseModel):
    id:              int
    alert_id:        int
    user_id:         str
    job_external_id: str
    job_id:          int | None
    job_title:       str
    company:         str
    score:           float
    seen:            bool
    created_at:      datetime

    model_config = {"from_attributes": True}
