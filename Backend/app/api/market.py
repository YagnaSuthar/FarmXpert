from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from app.core.config import get_db
from app.services.market_query_service import get_latest_prices

router = APIRouter(prefix="/api/v1/market", tags=["Market Intelligence"])


@router.get(
    "/prices",
    summary="Get latest mandi prices for a commodity",
    description="Returns raw price records from the database for a given commodity.",
)
async def get_prices(
    commodity: str = Query(
        ...,
        min_length=2,
        max_length=100,
        description="Commodity name, e.g. Wheat, Rice, Tomato",
        example="Wheat",
    ),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
):
    records = await get_latest_prices(db, commodity, limit=limit)

    if not records:
        raise HTTPException(
            status_code=404,
            detail=f"No price data available for commodity '{commodity}'.",
        )

    return [
        {
            "commodity": r.commodity,
            "market": r.market,
            "state": r.state,
            "district": r.district,
            "min_price": r.min_price,
            "max_price": r.max_price,
            "modal_price": r.modal_price,
            "arrival_date": r.arrival_date,
            "variety": r.variety,
            "grade": r.grade,
        }
        for r in records
    ]


@router.get(
    "/recommendation",
    summary="Get selling recommendation for a commodity",
    description=(
        "Calls the AI Market Intelligence Agent to analyze price data "
        "and return the best market recommendation."
    ),
)
async def get_recommendation(
    commodity: str = Query(
        ...,
        min_length=2,
        max_length=100,
        description="Commodity name, e.g. Wheat, Rice, Tomato",
        example="Wheat",
    ),
    db: AsyncSession = Depends(get_db),
):
    """
    Backend-side recommendation endpoint.
    Fetches data locally and runs logic for cases where
    AI_Backend is not available. For full agent pipeline,
    the AI_Backend endpoint should be used instead.
    """
    from app.services.market_query_service import get_latest_prices

    records = await get_latest_prices(db, commodity)

    if not records:
        raise HTTPException(
            status_code=404,
            detail=f"No market data available for commodity '{commodity}'.",
        )

    # Simple fallback logic (no AI agent dependency)
    valid = [r for r in records if r.modal_price and r.modal_price > 0]

    if not valid:
        raise HTTPException(
            status_code=404,
            detail=f"No valid price records for '{commodity}'.",
        )

    best = max(valid, key=lambda r: r.modal_price)
    n = len(valid)
    confidence = 0.85 if n > 20 else (0.6 if n > 5 else 0.3)

    return {
        "commodity": best.commodity,
        "best_market": best.market,
        "best_price": best.modal_price,
        "state": best.state,
        "district": best.district,
        "recommendation": "SELL",
        "confidence": round(confidence, 2),
    }
