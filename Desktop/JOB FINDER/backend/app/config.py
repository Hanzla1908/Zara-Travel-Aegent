from pathlib import Path
from pydantic_settings import BaseSettings

# Resolve .env from the project root whether uvicorn is run from backend/ or the root.
_here = Path(__file__).resolve().parent          # app/
_backend = _here.parent                          # backend/
_root = _backend.parent                          # project root
_env_file = _root / ".env" if (_root / ".env").exists() else _backend / ".env"


class Settings(BaseSettings):
    anthropic_api_key: str = ""
    database_url: str = "sqlite+aiosqlite:///./job_finder.db"
    debug: bool = False

    # LinkedIn Partner API — https://developer.linkedin.com/
    # Requires: Jobs on LinkedIn partner programme approval
    linkedin_access_token: str = ""

    # Rozee.pk Partner API — contact api@rozee.pk for access
    rozee_api_key: str = ""
    rozee_api_base: str = "https://api.rozee.pk/v1"

    # SMTP — required for email alert delivery.  All fields must be non-empty
    # before any email is sent.  No email is sent without both server-side SMTP
    # config AND the user setting email_enabled=true on their alert.
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_pass: str = ""
    smtp_from: str = ""

    model_config = {"env_file": str(_env_file)}


settings = Settings()
