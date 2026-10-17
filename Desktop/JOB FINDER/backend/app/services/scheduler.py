"""
Alert scheduler — asyncio background task that periodically checks due alerts.

Started during application lifespan; stopped gracefully on shutdown.
The poll interval is intentionally short (5 min) so that "Hourly" alerts
fire close to their target time.  The actual check uses each alert's own
frequency to decide whether it is due.
"""

from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)

_POLL_SECONDS = 300   # wake up every 5 minutes
_task: asyncio.Task | None = None


async def _loop() -> None:
    """Main scheduler loop. Runs until cancelled."""
    logger.info("Alert scheduler started (poll every %ds).", _POLL_SECONDS)
    while True:
        try:
            await asyncio.sleep(_POLL_SECONDS)
            await _run_once()
        except asyncio.CancelledError:
            logger.info("Alert scheduler stopped.")
            break
        except Exception as exc:
            logger.warning("Alert scheduler error: %s — will retry next cycle.", exc)


async def _run_once() -> None:
    from app.models.database import SessionLocal
    from app.services.alert_checker import check_all_due_alerts

    async with SessionLocal() as db:
        counts = await check_all_due_alerts(db)
        if counts:
            total = sum(counts.values())
            logger.info(
                "Alert cycle complete: %d new notification(s) across %d alert(s).",
                total, len(counts),
            )


def start() -> None:
    """Launch the scheduler background task. Safe to call multiple times."""
    global _task
    if _task is None or _task.done():
        _task = asyncio.create_task(_loop())


def stop() -> None:
    """Cancel the scheduler. Called on application shutdown."""
    global _task
    if _task and not _task.done():
        _task.cancel()
        _task = None
