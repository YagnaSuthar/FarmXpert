# ── MARKET INTELLIGENCE AGENT ─────────────────────────────
# Main entry point for the Market Intelligence Agent.

import logging
from typing import Optional

from agents.supplychain_market_access.market_intelligence.schemas import (
    MarketRecommendation,
    MarketQueryInput,
)
from agents.supplychain_market_access.market_intelligence.service import (
    generate_recommendation,
)

logger = logging.getLogger(__name__)


async def run_market_agent(
    input_data: MarketQueryInput,
    trend: Optional[str] = None,
) -> Optional[MarketRecommendation]:
    """
    Agent entry point.

    Args:
        input_data: MarketQueryInput with commodity + optional location context.
        trend: Optional price trend hint from upstream forecasting agent.

    Returns:
        MarketRecommendation or None if insufficient data.
    """
    logger.info(
        "Market Intelligence Agent invoked for '%s' (local: %s, district: %s).",
        input_data.commodity,
        input_data.local_market or "N/A",
        input_data.district or "N/A",
    )

    recommendation = await generate_recommendation(
        commodity=input_data.commodity,
        local_market=input_data.local_market,
        local_district=input_data.district,
        trend=trend,
    )

    if recommendation is None:
        logger.warning(
            "Agent could not produce a recommendation for '%s'.",
            input_data.commodity,
        )
        return None

    logger.info(
        "Agent result: %s at %s (₹%.2f profit, confidence %.0f%%)",
        recommendation.recommended_action,
        recommendation.best_market,
        recommendation.best_profit,
        recommendation.confidence * 100,
    )

    return recommendation
