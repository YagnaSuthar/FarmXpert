# ── ADVANCED DECISION LOGIC ────────────────────────────────
# Pure functions. No DB. No HTTP. Fully unit-testable.
# Operates on PriceRecord DTOs from schemas.py.

import logging
import statistics
from typing import Optional, List, Dict, Any

from AI_Backend.agents.supplychain_market_access.market_intelligence.schemas import (
    PriceRecord,
    RankedMarket,
)

logger = logging.getLogger(__name__)

# ── Transport cost defaults (placeholder until real model) ──
DEFAULT_TRANSPORT_COST_SAME_DISTRICT = 0.0
DEFAULT_TRANSPORT_COST_DIFF_DISTRICT = 100.0


# ─────────────────────────────────────────────────────────────
# 1. PROFIT CALCULATION
# ─────────────────────────────────────────────────────────────

def _estimate_transport_cost(
    record: PriceRecord,
    local_district: Optional[str] = None,
) -> float:
    """
    Estimate transport cost based on district proximity.

    Rules:
        - Same district as the farmer → 0
        - Different district           → flat ₹100 (placeholder)
    """
    if local_district and record.district:
        if record.district.strip().lower() == local_district.strip().lower():
            return DEFAULT_TRANSPORT_COST_SAME_DISTRICT

    return DEFAULT_TRANSPORT_COST_DIFF_DISTRICT


def _compute_profit(
    record: PriceRecord,
    local_district: Optional[str] = None,
) -> float:
    """Net profit = modal_price - transport_cost."""
    price = record.modal_price or 0.0
    transport = _estimate_transport_cost(record, local_district)
    return round(price - transport, 2)


# ─────────────────────────────────────────────────────────────
# 2. FIND BEST MARKET (by max profit)
# ─────────────────────────────────────────────────────────────

def find_best_market(
    records: List[PriceRecord],
    local_district: Optional[str] = None,
) -> Optional[PriceRecord]:
    """
    Select the record with the highest profit after transport cost.

    Args:
        records: List of PriceRecord DTOs.
        local_district: Farmer's district (used for transport cost calc).

    Returns:
        Best PriceRecord, or None if no valid data.
    """
    valid = [r for r in records if r.modal_price and r.modal_price > 0]

    if not valid:
        logger.warning("No records with a valid modal_price found.")
        return None

    best = max(valid, key=lambda r: _compute_profit(r, local_district))

    profit = _compute_profit(best, local_district)
    logger.info(
        "Best market: '%s' (%s) — price ₹%.2f, profit ₹%.2f",
        best.market,
        best.state or "N/A",
        best.modal_price,
        profit,
    )
    return best


# ─────────────────────────────────────────────────────────────
# 3. RANK TOP MARKETS
# ─────────────────────────────────────────────────────────────

def rank_markets(
    records: List[PriceRecord],
    local_district: Optional[str] = None,
    top_n: int = 3,
) -> List[RankedMarket]:
    """
    Return top N markets sorted by profit (descending).

    Deduplicates by market name — keeps the highest-profit entry per market.
    """
    valid = [r for r in records if r.modal_price and r.modal_price > 0]

    if not valid:
        return []

    # Deduplicate: keep best entry per market
    market_best: Dict[str, PriceRecord] = {}
    for r in valid:
        key = r.market.strip().lower()
        if key not in market_best:
            market_best[key] = r
        else:
            existing_profit = _compute_profit(market_best[key], local_district)
            current_profit = _compute_profit(r, local_district)
            if current_profit > existing_profit:
                market_best[key] = r

    # Sort by profit descending
    sorted_markets = sorted(
        market_best.values(),
        key=lambda r: _compute_profit(r, local_district),
        reverse=True,
    )

    ranked = []
    for i, r in enumerate(sorted_markets[:top_n], start=1):
        transport = _estimate_transport_cost(r, local_district)
        profit = _compute_profit(r, local_district)
        ranked.append(
            RankedMarket(
                rank=i,
                market=r.market,
                state=r.state,
                district=r.district,
                price=r.modal_price,
                profit=profit,
                transport_cost=transport,
            )
        )

    logger.info(
        "Ranked %d markets (from %d valid records).",
        len(ranked),
        len(valid),
    )
    return ranked


# ─────────────────────────────────────────────────────────────
# 4. DETERMINE ACTION
# ─────────────────────────────────────────────────────────────

def determine_action(
    best: PriceRecord,
    local_market: Optional[str] = None,
    local_district: Optional[str] = None,
    trend: Optional[str] = None,
) -> str:
    """
    Decide the recommended action.

    Rules:
        - If trend is "increasing" → HOLD (prices may rise further)
        - If best market != local market → SELL_IN_OTHER_MANDI
        - Otherwise → SELL_NOW

    Args:
        best: The best PriceRecord selected by find_best_market.
        local_market: Farmer's local/nearest market name.
        local_district: Farmer's district.
        trend: Price trend string ("increasing", "decreasing", "stable", None).

    Returns:
        One of: "SELL_NOW", "SELL_IN_OTHER_MANDI", "HOLD"
    """
    # Trend-based hold
    if trend and trend.strip().lower() == "increasing":
        logger.info("Trend is increasing — recommending HOLD.")
        return "HOLD"

    # Check if best market is different from local
    if local_market and best.market:
        if best.market.strip().lower() != local_market.strip().lower():
            logger.info(
                "Best market '%s' differs from local '%s' — SELL_IN_OTHER_MANDI.",
                best.market,
                local_market,
            )
            return "SELL_IN_OTHER_MANDI"

    logger.info("Recommending SELL_NOW at '%s'.", best.market)
    return "SELL_NOW"


# ─────────────────────────────────────────────────────────────
# 5. GENERATE HUMAN-READABLE REASON
# ─────────────────────────────────────────────────────────────

def generate_reason(
    best: PriceRecord,
    ranked: List[RankedMarket],
    action: str,
    local_district: Optional[str] = None,
) -> str:
    """
    Generate a human-readable explanation of the recommendation.

    Examples:
        "Surat mandi offers ₹200 higher profit than Ahmedabad after transport cost"
        "Sell at Ahmedabad — best profit with zero transport cost"
    """
    best_profit = _compute_profit(best, local_district)

    # If only one market
    if len(ranked) <= 1:
        return (
            f"{best.market} is the only available market with "
            f"₹{best.modal_price:.0f} modal price "
            f"(profit ₹{best_profit:.0f} after transport)."
        )

    # Compare with runner-up
    runner_up = ranked[1] if len(ranked) > 1 else None
    advantage = round(best_profit - runner_up.profit, 0) if runner_up else 0

    if action == "HOLD":
        return (
            f"Prices are trending upward. Current best is {best.market} "
            f"at ₹{best.modal_price:.0f} (profit ₹{best_profit:.0f}). "
            f"Consider holding for better prices."
        )

    if action == "SELL_IN_OTHER_MANDI":
        transport = _estimate_transport_cost(best, local_district)
        return (
            f"{best.market} mandi offers ₹{advantage:.0f} higher profit "
            f"than {runner_up.market} after ₹{transport:.0f} transport cost. "
            f"Best price: ₹{best.modal_price:.0f}, net profit: ₹{best_profit:.0f}."
        )

    # SELL_NOW
    if advantage > 0 and runner_up:
        return (
            f"Sell at {best.market} — ₹{advantage:.0f} more profitable "
            f"than {runner_up.market}. "
            f"Modal price ₹{best.modal_price:.0f}, profit ₹{best_profit:.0f}."
        )

    return (
        f"Sell at {best.market} — best available profit of ₹{best_profit:.0f} "
        f"at modal price ₹{best.modal_price:.0f}."
    )


# ─────────────────────────────────────────────────────────────
# 6. CALCULATE CONFIDENCE
# ─────────────────────────────────────────────────────────────

def calculate_confidence(
    records: List[PriceRecord],
    ranked: List[RankedMarket],
) -> float:
    """
    Compute a confidence score based on:
        1. Number of valid markets (data coverage)
        2. Price variance (consistency)
        3. Profit gap between top 2 markets (decisiveness)

    Returns:
        Float between 0.0 and 1.0.
    """
    valid_prices = [
        r.modal_price for r in records
        if r.modal_price and r.modal_price > 0
    ]

    if not valid_prices:
        return 0.0

    n_markets = len(set(r.market for r in records if r.modal_price and r.modal_price > 0))

    # ── Factor 1: Data coverage (0–0.35) ──────────────────
    if n_markets >= 15:
        coverage_score = 0.35
    elif n_markets >= 8:
        coverage_score = 0.25
    elif n_markets >= 3:
        coverage_score = 0.15
    else:
        coverage_score = 0.05

    # ── Factor 2: Price consistency (0–0.35) ──────────────
    # Low variance = more reliable data = higher confidence
    if len(valid_prices) >= 2:
        mean_price = statistics.mean(valid_prices)
        stdev = statistics.stdev(valid_prices)
        cv = stdev / mean_price if mean_price > 0 else 1.0  # coefficient of variation

        if cv < 0.05:
            consistency_score = 0.35   # very consistent
        elif cv < 0.15:
            consistency_score = 0.25
        elif cv < 0.30:
            consistency_score = 0.15
        else:
            consistency_score = 0.05   # high variance = low confidence
    else:
        consistency_score = 0.05

    # ── Factor 3: Decisiveness — gap between top 2 (0–0.30) ──
    if len(ranked) >= 2:
        gap = ranked[0].profit - ranked[1].profit
        gap_pct = gap / ranked[0].profit if ranked[0].profit > 0 else 0

        if gap_pct > 0.15:
            decisiveness_score = 0.30   # clear winner
        elif gap_pct > 0.05:
            decisiveness_score = 0.20
        elif gap_pct > 0.01:
            decisiveness_score = 0.10
        else:
            decisiveness_score = 0.05   # markets are very close
    else:
        decisiveness_score = 0.10

    confidence = round(coverage_score + consistency_score + decisiveness_score, 2)
    confidence = min(max(confidence, 0.0), 1.0)

    logger.info(
        "Confidence: %.2f (coverage=%.2f, consistency=%.2f, decisiveness=%.2f) "
        "| %d markets, %d prices",
        confidence,
        coverage_score,
        consistency_score,
        decisiveness_score,
        n_markets,
        len(valid_prices),
    )

    return confidence
