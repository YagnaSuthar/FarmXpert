import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.core.settings import settings
from app.tasks.market_tasks import fetch_and_store_mandi

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


def init_scheduler() -> None:
    """Register all recurring jobs and start the scheduler."""

    interval_minutes = settings.MANDI_FETCH_INTERVAL_MINUTES

    scheduler.add_job(
        fetch_and_store_mandi,
        trigger=IntervalTrigger(minutes=interval_minutes),
        id="mandi_ingestion",
        name="Mandi Price Ingestion Pipeline",
        replace_existing=True,
        max_instances=1,
    )

    scheduler.start()
    logger.info(
        "Scheduler started — mandi ingestion every %d minute(s).",
        interval_minutes,
    )


def shutdown_scheduler() -> None:
    """Gracefully shut down the scheduler."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler shut down.")
