from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.models.database import init_db
from app.services.seeder import seed_jobs
from app.models.database import SessionLocal
from app.api import jobs, cv, saved, alerts, workflow
from app.services import scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    async with SessionLocal() as db:
        seeded = await seed_jobs(db)
        if seeded:
            print(f"[startup] Seeded {seeded} jobs into the database.")
    scheduler.start()
    yield
    scheduler.stop()


app = FastAPI(
    title="AI Job Finder API",
    version="0.1.0",
    description="Backend for the AI-powered job finder agent.",
    lifespan=lifespan,
)

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
