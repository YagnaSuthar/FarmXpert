from fastapi import APIRouter, HTTPException, Query
from typing import Optional

from AI_Backend.agents.supplychain_market_access.market_intelligence.schemas import (
    MarketInsightsResponse,
    MarketQueryInput,
)
from AI_Backend.agents.supplychain_market_access.market_intelligence.agent import (
    run_market_agent,
)

router = APIRouter(prefix="/api/market-intelligence", tags=["Market Intelligence Agent"])


@router.get(
    "/insights",
    response_model=MarketInsightsResponse,
    summary="Commodity price insights — current and forecast",
    description=(
        "Returns current mandi prices, aggregated price stats, historical "
        "trend, and a forecast prediction for the given commodity. "
        "Insights only — no SELL/HOLD action and no transport/storage advice."
    ),
)
async def get_market_insights(
    commodity: str = Query(
        ..., min_length=2, max_length=100,
        description="Commodity name, e.g. Wheat, Rice, Tomato",
        example="Wheat",
    ),
    state: Optional[str] = Query(
        None,
        description="Optional regional filter — scopes the underlying fetch to a state.",
        example="Gujarat",
    ),
    district: Optional[str] = Query(
        None,
        description="Optional — annotates the snapshot with the farmer's district.",
        example="Ahmedabad",
    ),
    forecast_horizon_days: int = Query(
        7, ge=1, le=30,
        description="Days ahead the forecast targets (informational).",
    ),
):
    input_data = MarketQueryInput(
        commodity=commodity,
        state=state,
        district=district,
        forecast_horizon_days=forecast_horizon_days,
    )
    result = await run_market_agent(input_data)

    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"No price data available for '{commodity}'.",
        )
    return result
