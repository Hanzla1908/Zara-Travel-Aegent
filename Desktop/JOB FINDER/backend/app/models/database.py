from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    connect_args={"check_same_thread": False},
)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with SessionLocal() as session:
        yield session


async def _migrate(conn, table: str, columns: list[tuple[str, str]]) -> None:
    """ALTER TABLE ... ADD COLUMN for each (name, definition), silently skipping existing ones."""
    from sqlalchemy import text
    for col_name, col_def in columns:
        try:
            await conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_def}"))
        except Exception:
            pass  # column already exists


async def init_db() -> None:
    from app.models import Job, CVProfile, SavedJob, JobAlert, AlertNotification  # noqa: F401
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await _migrate(conn, "cv_profiles", [
            ("job_titles",  "JSON DEFAULT '[]'"),
            ("location",    "VARCHAR(255) DEFAULT ''"),
        ])
        await _migrate(conn, "jobs", [
            ("external_id", "VARCHAR(512) DEFAULT ''"),
            ("url",         "VARCHAR(1024) DEFAULT ''"),
        ])
        await _migrate(conn, "job_alerts", [
            ("min_score",       "REAL DEFAULT 0.0"),
            ("email_enabled",   "INTEGER DEFAULT 0"),
            ("email_address",   "VARCHAR(255) DEFAULT ''"),
            ("last_checked_at", "DATETIME"),
        ])
