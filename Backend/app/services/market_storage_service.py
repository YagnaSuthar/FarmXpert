import uuid
import logging
from typing import List

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.market_intelligence import MandiPriceData
from app.schemas.mandi import MandiPrice

logger = logging.getLogger(__name__)


async def save_mandi_data(
    db: AsyncSession,
    records: List[MandiPrice],
) -> int:
    """
    Persist mandi price records to the database.
    Deduplicates on (commodity, market, arrival_date) before inserting.

    Returns:
        Number of new records actually inserted.
    """
    if not records:
        logger.info("No records to save — skipping.")
        return 0

    # ── 1. Build a lookup of incoming keys ────────────────────────────
    incoming_keys = {
        (r.commodity, r.market, r.arrival_date) for r in records
    }

    # ── 2. Query existing keys in one round‑trip ──────────────────────
    try:
        existing_rows = await db.execute(
            select(
                MandiPriceData.commodity,
                MandiPriceData.market,
                MandiPriceData.arrival_date,
            ).where(
                and_(
                    MandiPriceData.commodity.in_([k[0] for k in incoming_keys]),
                    MandiPriceData.market.in_([k[1] for k in incoming_keys]),
                )
            )
        )
        existing_keys = {
            (row.commodity, row.market, row.arrival_date)
            for row in existing_rows.all()
        }
    except Exception:
        logger.exception("Failed to query existing mandi records")
        existing_keys = set()

    # ── 3. Filter duplicates ──────────────────────────────────────────
    new_records = [
        r for r in records
        if (r.commodity, r.market, r.arrival_date) not in existing_keys
    ]

    if not new_records:
        logger.info("All records already exist — nothing to insert.")
        return 0

    # ── 4. Convert Pydantic → ORM and bulk insert ─────────────────────
    db_objects = [
        MandiPriceData(
            id=uuid.uuid4(),
            commodity=r.commodity,
            market=r.market,
            state=r.state,
            district=r.district,
            min_price=r.min_price,
            max_price=r.max_price,
            modal_price=r.modal_price,
            arrival_date=r.arrival_date,
            variety=r.variety,
            grade=r.grade,
            source="AGMARKNET",
        )
        for r in new_records
    ]

    try:
        db.add_all(db_objects)
        await db.commit()
        logger.info(
            "Inserted %d new mandi price records (skipped %d duplicates).",
            len(db_objects),
            len(records) - len(db_objects),
        )
        return len(db_objects)

    except Exception:
        await db.rollback()
        logger.exception("Failed to insert mandi price records")
        return 0
