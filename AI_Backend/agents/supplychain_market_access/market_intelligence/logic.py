# ── MARKET INTELLIGENCE — DECISION LOGIC ──────────────────
# Pure functions ONLY.
# No HTTP calls. No DB access. No I/O side effects.
# Every function is independently unit-testable.
# All thresholds/constants imported from config.py.

from __future__ import annotations

import logging
import statistics
from typing import Dict, List, Optional

from agents.supplychain_market_access.market_intelligence.config import (
    FORECAST_DECREASE_THRESHOLD,
    FORECAST_INCREASE_THRESHOLD,
    HOLD_MIN_CONFIDENCE,
    MIN_PROFIT_TO_TRAVEL,
    MIN_RECORDS_FOR_TREND,
    STATE_ADJACENCY,
    TRANSPORT_ADJACENT_STATE,
    TRANSPORT_DISTANT_STATE,
    TRANSPORT_SAME_DISTRICT,
    TRANSPORT_SAME_MARKET,
    TRANSPORT_SAME_STATE,
    TREND_DECREASE_THRESHOLD,
    TREND_INCREASE_THRESHOLD,
)
from agents.supplychain_market_access.market_intelligence.schemas import (
    PriceRecord,
    RankedMarket,
)

logger = logging.getLogger(__name__)


# ═════════════════════════════════════════════════════════════
# 1.  TRANSPORT COST ESTIMATION
# ═════════════════════════════════════════════════════════════

def estimate_transport_cost(
    record: PriceRecord,
    local_market: Optional[str] = None,
    local_district: Optional[str] = None,
    local_state: Optional[str] = None,
) -> float:
    """
    Estimate transport cost (₹/quintal) using geographic proximity tiers.

    Tier hierarchy (first match wins):
        Same market     →  ₹0    (no travel)
        Same district   →  ₹50   (short haul)
        Same state      →  ₹150  (intra-state)
        Adjacent state  →  ₹300  (neighbouring state)
        Distant state   →  ₹500  (cross-country)

    All comparisons are case-insensitive and whitespace-normalised.
    """
    r_market   = (record.market   or "").strip().lower()
    r_district = (record.district or "").strip().lower()
    r_state    = (record.state    or "").strip().lower()

    l_market   = (local_market   or "").strip().lower()
    l_district = (local_district or "").strip().lower()
    l_state    = (local_state    or "").strip().lower()

    # Tier 1: same market
    if l_market and r_market and r_market == l_market:
        return TRANSPORT_SAME_MARKET

    # Tier 2: same district
    if l_district and r_district and r_district == l_district:
        return TRANSPORT_SAME_DISTRICT

    # Tier 3: same state
    if l_state and r_state and r_state == l_state:
        return TRANSPORT_SAME_STATE

    # Tier 4: adjacent state
    if l_state and r_state:
        neighbours = STATE_ADJACENCY.get(l_state, set())
        if r_state in neighbours:
            return TRANSPORT_ADJACENT_STATE

    # Tier 5: distant / unknown
    return TRANSPORT_DISTANT_STATE


# ═════════════════════════════════════════════════════════════
# 2.  PROFIT CALCULATION
# ═════════════════════════════════════════════════════════════

def calculate_profit(
    record: PriceRecord,
    local_market: Optional[str] = None,
    local_district: Optional[str] = None,
    local_state: Optional[str] = None,
) -> float:
    """
    Net profit = modal_price − transport_cost.

    Returns 0.0 when modal_price is absent/invalid (treated as unprofitable,
    not as an error — allows safe use in max() / sort).
    """
    price     = record.modal_price or 0.0
    transport = estimate_transport_cost(record, local_market, local_district, local_state)
    return round(price - transport, 2)


# ═════════════════════════════════════════════════════════════
# 3.  BEST MARKET SELECTION
# ═════════════════════════════════════════════════════════════

def find_best_market(
    records: List[PriceRecord],
    local_market: Optional[str] = None,
    local_district: Optional[str] = None,
    local_state: Optional[str] = None,
) -> Optional[PriceRecord]:
    """
    Return the PriceRecord with the highest net profit after transport.

    Args:
        records:        All fetched PriceRecord DTOs for the commodity.
        local_market:   Farmer's nearest mandi name.
        local_district: Farmer's district.
        local_state:    Farmer's state.

    Returns:
        Best PriceRecord, or None if no valid price data exists.
    """
    valid = [r for r in records if r.modal_price and r.modal_price > 0]

    if not valid:
        logger.warning("find_best_market: no records with valid modal_price.")
        return None

    best   = max(valid, key=lambda r: calculate_profit(r, local_market, local_district, local_state))
    profit = calculate_profit(best, local_market, local_district, local_state)

    logger.info(
        "Best market: '%s' (%s) — modal ₹%.2f | profit ₹%.2f",
        best.market, best.state or "N/A", best.modal_price, profit,
    )
    return best


# ═════════════════════════════════════════════════════════════
# 4.  MARKET RANKING
# ═════════════════════════════════════════════════════════════

def rank_markets(
    records: List[PriceRecord],
    local_market: Optional[str] = None,
    local_district: Optional[str] = None,
    local_state: Optional[str] = None,
    top_n: int = 3,
) -> List[RankedMarket]:
    """
    Rank unique markets by descending net profit and return the top N.

    Deduplication: when multiple records exist for the same market,
    keeps the one with the highest profit (most recent / highest price entry).

    Args:
        records:        All fetched PriceRecord DTOs.
        local_market:   Farmer's nearest mandi name.
        local_district: Farmer's district.
        local_state:    Farmer's state.
        top_n:          Number of markets to return (default 3).

    Returns:
        List of RankedMarket, sorted by profit descending, len ≤ top_n.
    """
    valid = [r for r in records if r.modal_price and r.modal_price > 0]
    if not valid:
        return []

    # Deduplicate: keep best-profit entry per market
    best_per_market: Dict[str, PriceRecord] = {}
    for r in valid:
        key = r.market.strip().lower()
        if key not in best_per_market:
            best_per_market[key] = r
        else:
            existing_profit = calculate_profit(best_per_market[key], local_market, local_district, local_state)
            current_profit  = calculate_profit(r,                    local_market, local_district, local_state)
            if current_profit > existing_profit:
                best_per_market[key] = r

    # Sort by profit descending
    sorted_records = sorted(
        best_per_market.values(),
        key=lambda r: calculate_profit(r, local_market, local_district, local_state),
        reverse=True,
    )

    ranked: List[RankedMarket] = []
    for i, r in enumerate(sorted_records[:top_n], start=1):
        transport = estimate_transport_cost(r, local_market, local_district, local_state)
        profit    = calculate_profit(r, local_market, local_district, local_state)
        ranked.append(
            RankedMarket(
                rank=i,
                market=r.market,
                state=r.state,
                district=r.district,
                price=r.modal_price,  # type: ignore[arg-type]
                profit=profit,
                transport_cost=transport,
            )
        )

    logger.info(
        "rank_markets: %d markets ranked (from %d valid records, top_n=%d).",
        len(ranked), len(valid), top_n,
    )
    return ranked


# ═════════════════════════════════════════════════════════════
# 5.  HISTORICAL TREND  (linear regression on modal_price)
# ═════════════════════════════════════════════════════════════

def calculate_trend(records: List[PriceRecord]) -> str:
    """
    Determine historical price trend using ordinary-least-squares slope.

    The slope is normalised by mean price so the threshold is
    scale-independent (works for ₹50 vegetables and ₹5000 grains alike).

    Args:
        records: Price records — ideally sorted oldest → newest.
                 Only records with valid modal_price are used.

    Returns:
        "increasing" | "decreasing" | "stable"
    """
    prices = [r.modal_price for r in records if r.modal_price and r.modal_price > 0]

    if len(prices) < MIN_RECORDS_FOR_TREND:
        logger.info(
            "calculate_trend: only %d valid prices (need %d) — returning 'stable'.",
            len(prices), MIN_RECORDS_FOR_TREND,
        )
        return "stable"

    n      = len(prices)
    x_mean = (n - 1) / 2.0
    y_mean = statistics.mean(prices)

    numerator   = sum((i - x_mean) * (prices[i] - y_mean) for i in range(n))
    denominator = sum((i - x_mean) ** 2                   for i in range(n))

    if denominator == 0:
        return "stable"

    slope            = numerator / denominator
    normalised_slope = slope / y_mean if y_mean > 0 else 0.0

    if normalised_slope > TREND_INCREASE_THRESHOLD:
        trend = "increasing"
    elif normalised_slope < TREND_DECREASE_THRESHOLD:
        trend = "decreasing"
    else:
        trend = "stable"

    logger.info(
        "calculate_trend: '%s' | slope=%.4f | normalised=%.4f | n=%d prices | mean=₹%.2f",
        trend, slope, normalised_slope, n, y_mean,
    )
    return trend


# ═════════════════════════════════════════════════════════════
# 6.  ACTION DECISION ENGINE
# ═════════════════════════════════════════════════════════════

def determine_action(
    best: PriceRecord,
    ranked: List[RankedMarket],
    local_market: Optional[str] = None,
    local_district: Optional[str] = None,
    local_state: Optional[str] = None,
    historical_trend: Optional[str] = None,
    predicted_trend: Optional[str] = None,
    confidence: float = 0.0,
) -> str:
    """
    Multi-signal decision engine.

    Priority rules evaluated top-down (first match wins):

    1. IMMEDIATE SELL if forecasted price is dropping
       → Predicted trend is "decreasing" AND confidence ≥ 0.3
       → Return SELL_NOW

    2. HOLD if both signals agree prices will rise AND confidence is sufficient
       → historical AND/OR predicted trend is "increasing"
       → Neither is "decreasing"
       → confidence ≥ HOLD_MIN_CONFIDENCE
       → Return HOLD

    3. SELL AT BETTER MANDI if a different market offers meaningful advantage
       → best market != farmer's local market
       → profit advantage ≥ MIN_PROFIT_TO_TRAVEL
       → Return SELL_IN_OTHER_MANDI

    4. Default: sell at best available market now
       → Return SELL_NOW

    Args:
        best:             Best PriceRecord selected by find_best_market.
        ranked:           Ranked market list (for profit comparison).
        local_market:     Farmer's nearest mandi.
        local_district:   Farmer's district.
        local_state:      Farmer's state.
        historical_trend: Output of calculate_trend().
        predicted_trend:  Output of predict_price_trend() from model_loader.
        confidence:       Confidence score from calculate_confidence().

    Returns:
        "SELL_NOW" | "SELL_IN_OTHER_MANDI" | "HOLD"
    """
    h = (historical_trend or "").strip().lower()
    p = (predicted_trend  or "").strip().lower()

    # ── Rule 1: Forecast signals price drop → sell immediately ──
    if p == "decreasing" and confidence >= 0.30:
        logger.info(
            "SELL_NOW: predicted trend='decreasing', confidence=%.2f — price expected to fall.",
            confidence,
        )
        return "SELL_NOW"

    # ── Rule 2: Hold while prices are rising ──────────────────
    either_increasing   = (h == "increasing" or p == "increasing")
    neither_decreasing  = (h != "decreasing" and p != "decreasing")

    if either_increasing and neither_decreasing and confidence >= HOLD_MIN_CONFIDENCE:
        logger.info(
            "HOLD: hist='%s', pred='%s', confidence=%.2f — prices trending upward.",
            h, p, confidence,
        )
        return "HOLD"

    # ── Rule 3: Better profit at another mandi ────────────────
    if local_market and best.market:
        is_different = best.market.strip().lower() != local_market.strip().lower()

        if is_different:
            best_profit = calculate_profit(best, local_market, local_district, local_state)

            # Look up local market profit from ranked list
            local_profit = 0.0
            for m in ranked:
                if m.market.strip().lower() == local_market.strip().lower():
                    local_profit = m.profit
                    break

            profit_advantage = best_profit - local_profit

            if profit_advantage >= MIN_PROFIT_TO_TRAVEL:
                logger.info(
                    "SELL_IN_OTHER_MANDI: '%s' has ₹%.2f advantage over local '%s'.",
                    best.market, profit_advantage, local_market,
                )
                return "SELL_IN_OTHER_MANDI"

            logger.info(
                "Best market '%s' differs from local '%s' but advantage ₹%.2f < threshold ₹%.2f — SELL_NOW.",
                best.market, local_market, profit_advantage, MIN_PROFIT_TO_TRAVEL,
            )

    # ── Rule 4: Default ───────────────────────────────────────
    logger.info("SELL_NOW at '%s' — no superior alternative or hold condition met.", best.market)
    return "SELL_NOW"


# ═════════════════════════════════════════════════════════════
# 7.  HUMAN-READABLE REASON GENERATION
# ═════════════════════════════════════════════════════════════

def generate_reason(
    best: PriceRecord,
    ranked: List[RankedMarket],
    action: str,
    local_market: Optional[str] = None,
    local_district: Optional[str] = None,
    local_state: Optional[str] = None,
    historical_trend: Optional[str] = None,
    predicted_trend: Optional[str] = None,
    predicted_price: Optional[float] = None,
) -> str:
    """
    Generate a concise, farmer-friendly explanation of the recommendation.

    Language is kept actionable and quantitative — farmers respond better
    to concrete ₹ numbers than abstract signals.
    """
    best_profit = calculate_profit(best, local_market, local_district, local_state)
    transport   = estimate_transport_cost(best, local_market, local_district, local_state)
    runner_up   = ranked[1] if len(ranked) > 1 else None
    advantage   = round(best_profit - runner_up.profit, 0) if runner_up else 0.0

    # Build forecast note
    forecast_note = ""
    if predicted_price and predicted_price > 0 and predicted_trend:
        direction_word = {
            "increasing": "rise",
            "decreasing": "fall",
            "stable":     "remain stable",
        }.get(predicted_trend, "change")
        forecast_note = (
            f" Forecast: price expected to {direction_word} "
            f"to ₹{predicted_price:.0f}."
        )
    elif historical_trend and historical_trend != "stable":
        forecast_note = f" Historical trend: {historical_trend}."

    # ── HOLD ──────────────────────────────────────────────────
    if action == "HOLD":
        return (
            f"Prices at {best.market} are trending upward "
            f"(modal ₹{best.modal_price:.0f}, net profit ₹{best_profit:.0f}).{forecast_note} "
            f"Holding for a few days may yield a better return."
        )

    # ── Only one market available ─────────────────────────────
    if len(ranked) <= 1:
        return (
            f"Only one market found: {best.market} at ₹{best.modal_price:.0f}/qtl "
            f"(net profit ₹{best_profit:.0f} after ₹{transport:.0f} transport).{forecast_note}"
        )

    # ── SELL_IN_OTHER_MANDI ───────────────────────────────────
    if action == "SELL_IN_OTHER_MANDI":
        return (
            f"{best.market} offers ₹{advantage:.0f} higher net profit than "
            f"{runner_up.market} "  # type: ignore[union-attr]
            f"(₹{best_profit:.0f} vs ₹{runner_up.profit:.0f}) "  # type: ignore[union-attr]
            f"after ₹{transport:.0f} transport cost.{forecast_note}"
        )

    # ── SELL_NOW ──────────────────────────────────────────────
    if advantage > 0 and runner_up:
        return (
            f"Sell at {best.market} — ₹{advantage:.0f} more profitable than "
            f"{runner_up.market} "
            f"(₹{best_profit:.0f} vs ₹{runner_up.profit:.0f}).{forecast_note}"
        )

    return (
        f"Sell at {best.market} — best available net profit "
        f"₹{best_profit:.0f} at modal price ₹{best.modal_price:.0f}.{forecast_note}"
    )


# ═════════════════════════════════════════════════════════════
# 8.  CONFIDENCE SCORE
# ═════════════════════════════════════════════════════════════

def calculate_confidence(
    records: List[PriceRecord],
    ranked: List[RankedMarket],
    historical_trend: Optional[str] = None,
    predicted_trend: Optional[str] = None,
) -> float:
    """
    Compute a composite confidence score in [0.0, 1.0].

    Four independent factors (weights sum to 1.0):

    ┌─────────────────────────────────────────────────────────┐
    │ Factor                 │ Weight │ Measures               │
    ├─────────────────────────────────────────────────────────┤
    │ 1. Data coverage       │  0.30  │ Number of unique mandis │
    │ 2. Price consistency   │  0.30  │ Coefficient of variation│
    │ 3. Decisiveness        │  0.25  │ Profit gap top-1 vs top-2│
    │ 4. Signal agreement    │  0.15  │ hist & pred trend align │
    └─────────────────────────────────────────────────────────┘

    Returns 0.0 if no valid price data is available.
    """
    valid_prices = [
        r.modal_price for r in records
        if r.modal_price and r.modal_price > 0
    ]
    if not valid_prices:
        return 0.0

    n_markets = len(
        {r.market.strip().lower() for r in records
         if r.modal_price and r.modal_price > 0}
    )

    # ── Factor 1: Data coverage (0 – 0.30) ───────────────────
    if n_markets >= 20:
        f_coverage = 0.30
    elif n_markets >= 12:
        f_coverage = 0.24
    elif n_markets >= 6:
        f_coverage = 0.16
    elif n_markets >= 3:
        f_coverage = 0.10
    else:
        f_coverage = 0.04

    # ── Factor 2: Price consistency (0 – 0.30) ───────────────
    # Coefficient of variation (CV = std / mean): lower CV → higher confidence
    if len(valid_prices) >= 2:
        y_mean = statistics.mean(valid_prices)
        stdev  = statistics.stdev(valid_prices)
        cv     = stdev / y_mean if y_mean > 0 else 1.0

        if cv < 0.05:
            f_consistency = 0.30
        elif cv < 0.12:
            f_consistency = 0.22
        elif cv < 0.25:
            f_consistency = 0.14
        elif cv < 0.40:
            f_consistency = 0.08
        else:
            f_consistency = 0.03
    else:
        f_consistency = 0.04

    # ── Factor 3: Decisiveness (0 – 0.25) ────────────────────
    # Large gap between best and second-best → clear winner → higher confidence
    if len(ranked) >= 2 and ranked[0].profit > 0:
        gap_pct = (ranked[0].profit - ranked[1].profit) / ranked[0].profit

        if gap_pct > 0.20:
            f_decisive = 0.25
        elif gap_pct > 0.10:
            f_decisive = 0.18
        elif gap_pct > 0.04:
            f_decisive = 0.11
        else:
            f_decisive = 0.04   # markets nearly identical → uncertain
    elif len(ranked) == 1:
        f_decisive = 0.12       # single market — no comparison possible
    else:
        f_decisive = 0.04

    # ── Factor 4: Signal agreement (0 – 0.15) ────────────────
    h = (historical_trend or "").lower()
    p = (predicted_trend  or "").lower()

    if h and p:
        if h == p:
            f_signal = 0.15   # both signals agree
        elif {h, p} == {"increasing", "decreasing"}:
            f_signal = 0.00   # directly contradictory → penalise
        else:
            f_signal = 0.07   # partial agreement (one stable, one directional)
    elif h or p:
        f_signal = 0.07       # only one signal available
    else:
        f_signal = 0.05       # no trend signals at all

    confidence = round(f_coverage + f_consistency + f_decisive + f_signal, 2)
    confidence = min(max(confidence, 0.0), 1.0)

    logger.info(
        "Confidence: %.2f "
        "[coverage=%.2f | consistency=%.2f | decisive=%.2f | signal=%.2f] "
        "| markets=%d | prices=%d",
        confidence,
        f_coverage, f_consistency, f_decisive, f_signal,
        n_markets, len(valid_prices),
    )
    return confidence