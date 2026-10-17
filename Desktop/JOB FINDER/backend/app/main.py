import logging
import logging.config
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.models.database import init_db
from app.services.seeder import seed_jobs
from app.models.database import SessionLocal
from app.api import jobs, cv, saved, alerts, workflow
from app.services import scheduler
from app.middleware.rate_limit import RateLimitMiddleware

# ---------------------------------------------------------------------------
# Logging configuration
# ---------------------------------------------------------------------------

logging.config.dictConfig({
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {
            "format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S",
        }
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "default",
            "stream": "ext://sys.stdout",
        }
    },
    "root": {"level": "INFO", "handlers": ["console"]},
    # Suppress noisy third-party loggers
    "loggers": {
        "httpx":          {"level": "WARNING", "propagate": True},
        "httpcore":       {"level": "WARNING", "propagate": True},
        "anthropic":      {"level": "WARNING", "propagate": True},
        "uvicorn.access": {"level": "WARNING", "propagate": True},
    },
})

_log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    async with SessionLocal() as db:
        seeded = await seed_jobs(db)
        if seeded:
            _log.info("Startup: seeded %d jobs into the database.", seeded)
    scheduler.start()
    _log.info("Startup complete. Alert scheduler started.")
    yield
    scheduler.stop()
    _log.info("Shutdown: alert scheduler stopped.")


app = FastAPI(
    title="AI Job Finder API",
    version="0.1.0",
    description="Backend for the AI-powered job finder agent.",
    lifespan=lifespan,
)

# Rate limiting must be added before CORS so it fires first.
app.add_middleware(RateLimitMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(jobs.router,   prefix="/api/jobs",   tags=["Jobs"])
app.include_router(cv.router,     prefix="/api/cv",     tags=["CV"])
app.include_router(saved.router,  prefix="/api/saved",  tags=["Saved Jobs"])
app.include_router(alerts.router,   prefix="/api/alerts",   tags=["Alerts"])
app.include_router(workflow.router, prefix="/api/workflow", tags=["Workflow"])


@app.get("/health", tags=["Health"])
async def health():
    return {"status": "ok", "version": app.version}
