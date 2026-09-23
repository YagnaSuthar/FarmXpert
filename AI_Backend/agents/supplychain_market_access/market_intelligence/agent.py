# ── MARKET INTELLIGENCE — AGENT ENTRY POINT (v3.0) ────────
# Thin coordination layer. Delegates entirely to service.generate_insights.

from __future__ import annotations

import logging
from typing import Optional

from AI_Backend.agents.supplychain_market_access.market_intelligence.schemas import (
    MarketInsights,
    MarketQueryInput,
)
from AI_Backend.agents.supplychain_market_access.market_intelligence.service import (
    generate_insights,
)
from AI_Backend.agents.supplychain_market_access.market_intelligence.config import (
    AGENT_ID,
    AGENT_VERSION,
)

logger = logging.getLogger(__name__)


async def run_market_agent(
    input_data: MarketQueryInput,
) -> Optional[MarketInsights]:
    """
    Market Intelligence Agent — public entry point (v3.0).

    Returns commodity price insights ONLY:
        • Per-market price table
        • Aggregated price summary
        • Historical trend
        • Forecast prediction (LSTM / WMA / fallback)
        • Confidence + data-quality signals

    No SELL/HOLD action, no transport / profit, no storage suggestions.
    The orchestrator turns these structured insights into farmer prose.

    Args:
        input_data: MarketQueryInput validated by the router.

    Returns:
        MarketInsights, or None if there's no usable price data.
    """
    logger.info(
        "Market Intelligence v%s | commodity='%s' | state='%s' | district='%s'",
        AGENT_VERSION,
        input_data.commodity,
        input_data.state or "—",
        input_data.district or "—",
    )

    insights = await generate_insights(
        commodity=input_data.commodity,
        state=input_data.state,
        district=input_data.district,
        forecast_horizon_days=input_data.forecast_horizon_days,
    )

    if insights is None:
        logger.warning(
            "Market Intelligence | commodity='%s' → NO INSIGHTS (insufficient data).",
            input_data.commodity,
        )
        return None

    logger.info(
        "Market Intelligence | commodity='%s' | markets=%d | hist=%s | pred=%s | conf=%.0f%%",
        input_data.commodity,
        insights.price_summary.sampled_markets,
        insights.price_trend.direction,
        insights.forecast.predicted_trend,
        insights.confidence * 100,
    )
    return insights
