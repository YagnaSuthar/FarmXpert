import logging

from app.core.config import AsyncSessionLocal
from app.core.settings import settings
from app.services.mandi_service import mandi_service
from app.services.market_storage_service import save_mandi_data

logger = logging.getLogger(__name__)


async def fetch_and_store_mandi() -> None:
    """
    Background task: fetch mandi prices for configured commodities
    and persist them to the database.
    """
    commodities = settings.MANDI_COMMODITIES
    logger.info("Starting mandi ingestion for: %s", commodities)

    total_inserted = 0

    async with AsyncSessionLocal() as db:
        for commodity in commodities:
            try:
                logger.info("Fetching prices for '%s' ...", commodity)
                records = await mandi_service.fetch_prices(
                    commodity=commodity,
                    limit=100,
                )

                if not records:
                    logger.warning("No data returned for '%s'.", commodity)
                    continue

                inserted = await save_mandi_data(db, records)
                total_inserted += inserted
                logger.info(
                    "'%s': fetched %d, inserted %d.",
                    commodity,
                    len(records),
                    inserted,
                )

            except Exception:
                logger.exception(
                    "Failed to process commodity '%s'.", commodity
                )

    logger.info(
        "Mandi ingestion complete — %d total new records.", total_inserted
    )
