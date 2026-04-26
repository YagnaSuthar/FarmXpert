from fastapi import APIRouter, HTTPException, Query
from typing import Optional

from agents.supplychain_market_access.market_intelligence.schemas import (
    MarketQueryInput,
    MarketRecommendationResponse,
)
from agents.supplychain_market_access.market_intelligence.agent import (
    run_market_agent,
)

router = APIRouter(prefix="/api/market-intelligence", tags=["Market Intelligence Agent"])


@router.get(
    "/recommendation",
    response_model=MarketRecommendationResponse,
    summary="AI-powered selling recommendation",
    description=(
        "Invokes the Market Intelligence Agent to analyze mandi prices "
        "and return the optimal profit-based selling recommendation."
    ),
)
async def get_ai_recommendation(
    commodity: str = Query(
        ...,
        min_length=2,
        max_length=100,
        description="Commodity name, e.g. Wheat, Rice, Tomato",
        example="Wheat",
    ),
    local_market: Optional[str] = Query(
        None,
        description="Farmer's local/nearest market name",
        example="Ahmedabad",
    ),
    district: Optional[str] = Query(
        None,
        description="Farmer's district (for transport cost estimation)",
        example="Ahmedabad",
    ),
    trend: Optional[str] = Query(
        None,
        description="Price trend hint: increasing, decreasing, stable",
        example="stable",
    ),
):
    input_data = MarketQueryInput(
        commodity=commodity,
        local_market=local_market,
        district=district,
    )
    result = await run_market_agent(input_data, trend=trend)

    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"Agent could not generate recommendation for '{commodity}'.",
        )

    return result
