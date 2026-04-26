import logging
from typing import List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.market_intelligence import MandiPriceData

logger = logging.getLogger(__name__)


async def get_latest_prices(
    db: AsyncSession,
    commodity: str,
    limit: int = 100,
) -> List[MandiPriceData]:
    """
    Fetch the most recent mandi price records for a given commodity.

    Args:
        db: Async database session.
        commodity: Commodity name (case-insensitive match).
        limit: Max rows to return (default 100).

    Returns:
        List of MandiPriceData ORM objects ordered by recorded_at DESC.
    """
    try:
        stmt = (
            select(MandiPriceData)
            .where(MandiPriceData.commodity.ilike(commodity))
            .order_by(MandiPriceData.recorded_at.desc())
            .limit(limit)
        )
        result = await db.execute(stmt)
        records = result.scalars().all()

        logger.info(
            "Fetched %d recent records for commodity '%s'.",
            len(records),
            commodity,
        )
        return list(records)

    except Exception:
        logger.exception(
            "Failed to query latest prices for '%s'.", commodity
        )
        return []
