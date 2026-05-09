# ── MARKET INTELLIGENCE — AGENT ENTRY POINT ───────────────
# Thin coordination layer.
# Contains NO business logic — delegates entirely to service.py.
# Called by the router (routers/market_intelligence.py).

from __future__ import annotations

import logging
from typing import Optional

from agents.supplychain_market_access.market_intelligence.schemas import (
    MarketQueryInput,
    MarketRecommendation,
)
from AI_Backend.agents.supplychain_market_access.market_intelligence.service import (
    generate_recommendation,
)

logger = logging.getLogger(__name__)


async def run_market_agent(
    input_data: MarketQueryInput,
) -> Optional[MarketRecommendation]:
    """
    Market Intelligence Agent — public entry point.

    Accepts a validated MarketQueryInput and returns a full
    MarketRecommendation with:
        • recommended action  (SELL_NOW / SELL_IN_OTHER_MANDI / HOLD)
        • best market & net profit
        • top 3 markets ranked by profit
        • human-readable reason
        • historical trend + LSTM forecast
        • multi-factor confidence score

    The agent is stateless — every call is self-contained.
    No DB access, no session state, no side effects.

    Args:
        input_data: MarketQueryInput validated by the router.

    Returns:
        MarketRecommendation, or None if insufficient mandi data.
    """
    logger.info(
        "▶ Market Intelligence Agent | commodity='%s' | "
        "market='%s' | district='%s' | state='%s'",
        input_data.commodity,
        input_data.local_market or "—",
        input_data.district     or "—",
        input_data.state        or "—",
    )

    recommendation = await generate_recommendation(
        commodity=input_data.commodity,
        local_market=input_data.local_market,
        local_district=input_data.district,
        local_state=input_data.state,
    )

    if recommendation is None:
        logger.warning(
            "◀ Market Intelligence Agent | commodity='%s' → NO RECOMMENDATION "
            "(insufficient mandi data).",
            input_data.commodity,
        )
        return None

    logger.info(
        "◀ Market Intelligence Agent | commodity='%s' → %s at '%s' | "
        "profit=₹%.2f | confidence=%.0f%% | trend=%s | forecast=%s",
        input_data.commodity,
        recommendation.recommended_action,
        recommendation.best_market,
        recommendation.best_profit,
        recommendation.confidence * 100,
        recommendation.trend         or "N/A",
        recommendation.predicted_trend or "N/A",
    )

    return recommendation