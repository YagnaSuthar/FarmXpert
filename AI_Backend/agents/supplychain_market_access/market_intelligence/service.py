# ── ORCHESTRATION SERVICE ──────────────────────────────────
# Coordinates data fetching (via Backend API) and decision logic.
# AI_Backend NEVER touches the DB directly.

import logging
import httpx
from typing import Optional, List

from agents.supplychain_market_access.market_intelligence.config import (
    BACKEND_BASE_URL,
)
from agents.supplychain_market_access.market_intelligence.schemas import (
    PriceRecord,
    MarketRecommendation,
)
from agents.supplychain_market_access.market_intelligence.logic import (
    find_best_market,
    rank_markets,
    determine_action,
    generate_reason,
    calculate_confidence,
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────
# DATA FETCHING (Backend API)
# ─────────────────────────────────────────────────────────────

async def fetch_prices_from_backend(
    commodity: str,
    limit: int = 100,
) -> List[PriceRecord]:
    """
    Call the Backend query API to get latest mandi prices.
    AI_Backend accesses data through the Backend API — not the DB.
    """
    url = f"{BACKEND_BASE_URL}/api/v1/market/prices"
    params = {"commodity": commodity, "limit": limit}

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()

            data = response.json()
            records = [PriceRecord(**item) for item in data]

            logger.info(
                "Fetched %d price records for '%s' from Backend.",
                len(records),
                commodity,
            )
            return records

    except httpx.HTTPStatusError as e:
        logger.error(
            "Backend returned %d for commodity '%s'.",
            e.response.status_code,
            commodity,
        )
        return []

    except Exception:
        logger.exception("Failed to fetch prices from Backend for '%s'.", commodity)
        return []


# ─────────────────────────────────────────────────────────────
# RECOMMENDATION PIPELINE
# ─────────────────────────────────────────────────────────────

async def generate_recommendation(
    commodity: str,
    local_market: Optional[str] = None,
    local_district: Optional[str] = None,
    trend: Optional[str] = None,
) -> Optional[MarketRecommendation]:
    """
    End-to-end intelligent recommendation pipeline.

    Steps:
        1. Fetch prices from Backend API.
        2. Find best market (by MAX PROFIT, not price).
        3. Rank top 3 markets.
        4. Determine action (SELL_NOW / SELL_IN_OTHER_MANDI / HOLD).
        5. Generate human-readable reason.
        6. Calculate multi-factor confidence score.
        7. Return structured MarketRecommendation.

    Args:
        commodity: Crop name (e.g. "Wheat").
        local_market: Farmer's nearest market (for action logic).
        local_district: Farmer's district (for transport cost calc).
        trend: Price trend hint ("increasing", "decreasing", "stable", None).

    Returns:
        MarketRecommendation or None if insufficient data.
    """
    # ── 1. Fetch data ─────────────────────────────────────
    records = await fetch_prices_from_backend(commodity)

    if not records:
        logger.warning("No data for '%s' — cannot recommend.", commodity)
        return None

    # ── 2. Find best market (profit-based) ────────────────
    best = find_best_market(records, local_district=local_district)

    if best is None:
        logger.warning("No valid market for '%s'.", commodity)
        return None

    # ── 3. Rank top markets ───────────────────────────────
    ranked = rank_markets(records, local_district=local_district, top_n=3)

    # ── 4. Determine action ───────────────────────────────
    action = determine_action(
        best,
        local_market=local_market,
        local_district=local_district,
        trend=trend,
    )

    # ── 5. Generate explanation ───────────────────────────
    reason = generate_reason(
        best,
        ranked,
        action,
        local_district=local_district,
    )

    # ── 6. Calculate confidence ───────────────────────────
    confidence = calculate_confidence(records, ranked)

    # ── 7. Build recommendation ───────────────────────────
    from agents.supplychain_market_access.market_intelligence.logic import _compute_profit

    best_profit = _compute_profit(best, local_district)

    recommendation = MarketRecommendation(
        commodity=best.commodity,
        best_market=best.market,
        best_price=best.modal_price,
        best_profit=best_profit,
        recommended_action=action,
        top_markets=ranked,
        reason=reason,
        confidence=confidence,
    )

    logger.info(
        "Recommendation for '%s': %s at '%s' | price ₹%.2f | profit ₹%.2f | confidence %.0f%%",
        commodity,
        action,
        best.market,
        best.modal_price,
        best_profit,
        confidence * 100,
    )

    return recommendation
