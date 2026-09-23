# ── MARKET INTELLIGENCE — INSIGHTS HELPERS (v3.0) ─────────
# Pure functions ONLY. No HTTP, no DB, no I/O side effects.
# v3.0 dropped: estimate_transport_cost, calculate_profit, find_best_market,
#                rank_markets, determine_action, generate_reason.
# Kept and refactored: calculate_trend, calculate_confidence.
# Added: build_market_prices, build_price_summary, fresh_records_pct.

from __future__ import annotations

import logging
import statistics
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional

from AI_Backend.agents.supplychain_market_access.market_intelligence.config import (
    FRESH_RECORD_WINDOW_DAYS,
    MARKETS_TO_RETURN,
    MIN_RECORDS_FOR_TREND,
    TREND_DECREASE_THRESHOLD,
    TREND_INCREASE_THRESHOLD,
)
from AI_Backend.agents.supplychain_market_access.market_intelligence.schemas import (
    MarketPrice,
    PriceRecord,
    PriceSummary,
)

logger = logging.getLogger(__name__)


# ═════════════════════════════════════════════════════════════
# 1.  PER-MARKET SNAPSHOT
# ═════════════════════════════════════════════════════════════

def build_market_prices(
    records: List[PriceRecord],
    *,
    top_n: int = MARKETS_TO_RETURN,
) -> List[MarketPrice]:
    """
    Deduplicate by market name and surface the freshest row per market.
    Sorted by modal_price descending so the highest price appears first.

    No profit calculation — that involves transport cost which v3 removed.
    """
    valid = [r for r in records if r.modal_price and r.modal_price > 0]
    if not valid:
        return []

    # Keep the freshest record per market name (case-insensitive).
    by_market: Dict[str, PriceRecord] = {}
    for r in valid:
        key = (r.market or "").strip().lower()
        if not key:
            continue
        prev = by_market.get(key)
        if prev is None or _date_or_min(r.arrival_date) > _date_or_min(prev.arrival_date):
            by_market[key] = r

    rows = sorted(
        by_market.values(),
        key=lambda r: (r.modal_price or 0.0),
        reverse=True,
    )

    return [
        MarketPrice(
            market=r.market,
            state=r.state,
            district=r.district,
            modal_price=float(r.modal_price),   # validated > 0 above
            min_price=r.min_price,
            max_price=r.max_price,
            arrival_date=r.arrival_date,
            variety=r.variety,
            grade=r.grade,
        )
        for r in rows[:top_n]
    ]


# ═════════════════════════════════════════════════════════════
# 2.  AGGREGATED PRICE SUMMARY
# ═════════════════════════════════════════════════════════════

def build_price_summary(records: List[PriceRecord]) -> Optional[PriceSummary]:
    """Compute min / max / avg / median + spread % over the snapshot."""
    modals = [float(r.modal_price) for r in records if r.modal_price and r.modal_price > 0]
    if not modals:
        return None

    mins = [float(r.min_price) for r in records if r.min_price and r.min_price > 0]
    maxs = [float(r.max_price) for r in records if r.max_price and r.max_price > 0]

    avg = statistics.fmean(modals)
    lo  = min(modals)
    hi  = max(modals)
    spread_pct = ((hi - lo) / avg * 100.0) if avg > 0 else 0.0

    unique_markets = len({(r.market or "").strip().lower() for r in records
                          if r.modal_price and r.modal_price > 0})

    return PriceSummary(
        modal_price_avg=round(avg, 2),
        modal_price_min=round(lo, 2),
        modal_price_max=round(hi, 2),
        modal_price_median=round(statistics.median(modals), 2),
        min_price_avg=round(statistics.fmean(mins), 2) if mins else None,
        max_price_avg=round(statistics.fmean(maxs), 2) if maxs else None,
        spread_pct=round(spread_pct, 1),
        sampled_markets=unique_markets,
        sampled_records=len(modals),
    )


# ═════════════════════════════════════════════════════════════
# 3.  HISTORICAL TREND (OLS slope on modal_price)
# ═════════════════════════════════════════════════════════════

def calculate_trend(records: List[PriceRecord]) -> Dict[str, float | str | int]:
    """
    OLS slope on modal_price across the fetched window.

    Scale-independent: slope is normalised by mean so the ±2 % threshold
    works for ₹50 vegetables and ₹5000 grains alike.

    Returns: {"direction": ..., "slope_normalised": ..., "window_records": n}
    """
    prices = [r.modal_price for r in records if r.modal_price and r.modal_price > 0]
    n = len(prices)

    if n < MIN_RECORDS_FOR_TREND:
        return {"direction": "stable", "slope_normalised": 0.0, "window_records": n}

    x_mean = (n - 1) / 2.0
    y_mean = statistics.fmean(prices)

    numerator   = sum((i - x_mean) * (prices[i] - y_mean) for i in range(n))
    denominator = sum((i - x_mean) ** 2                   for i in range(n))

    if denominator == 0 or y_mean <= 0:
        return {"direction": "stable", "slope_normalised": 0.0, "window_records": n}

    slope = numerator / denominator
    normalised = slope / y_mean

    if normalised > TREND_INCREASE_THRESHOLD:
        direction = "increasing"
    elif normalised < TREND_DECREASE_THRESHOLD:
        direction = "decreasing"
    else:
        direction = "stable"

    return {
        "direction": direction,
        "slope_normalised": round(normalised, 4),
        "window_records": n,
    }


# ═════════════════════════════════════════════════════════════
# 4.  CONFIDENCE
# ═════════════════════════════════════════════════════════════

def calculate_confidence(
    records: List[PriceRecord],
    historical_trend: str,
    predicted_trend: str,
) -> float:
    """
    Composite score in [0, 1] from three factors:

        ┌─────────────────────────────────────────────────────┐
        │ Factor              │ Weight │ Measures              │
        ├─────────────────────────────────────────────────────┤
        │ 1. Data coverage    │  0.40  │ Unique markets         │
        │ 2. Price consistency│  0.40  │ Coefficient of variation│
        │ 3. Signal agreement │  0.20  │ Hist vs forecast align │
        └─────────────────────────────────────────────────────┘
    """
    valid_prices = [r.modal_price for r in records
                    if r.modal_price and r.modal_price > 0]
    if not valid_prices:
        return 0.0

    n_markets = len({(r.market or "").strip().lower() for r in records
                     if r.modal_price and r.modal_price > 0})

    # 1. Data coverage
    if   n_markets >= 20: f_coverage = 0.40
    elif n_markets >= 12: f_coverage = 0.32
    elif n_markets >=  6: f_coverage = 0.22
    elif n_markets >=  3: f_coverage = 0.14
    else:                 f_coverage = 0.06

    # 2. Price consistency (low CV → high confidence)
    if len(valid_prices) >= 2:
        y_mean = statistics.fmean(valid_prices)
        stdev  = statistics.stdev(valid_prices) if y_mean > 0 else 0.0
        cv     = stdev / y_mean if y_mean > 0 else 1.0
        if   cv < 0.05: f_consistency = 0.40
        elif cv < 0.12: f_consistency = 0.30
        elif cv < 0.25: f_consistency = 0.18
        elif cv < 0.40: f_consistency = 0.10
        else:           f_consistency = 0.04
    else:
        f_consistency = 0.05

    # 3. Signal agreement
    h = (historical_trend or "").lower()
    p = (predicted_trend  or "").lower()
    if h and p:
        if h == p:                                       f_signal = 0.20
        elif {h, p} == {"increasing", "decreasing"}:     f_signal = 0.00   # contradiction
        else:                                            f_signal = 0.10
    elif h or p:
        f_signal = 0.10
    else:
        f_signal = 0.05

    score = round(f_coverage + f_consistency + f_signal, 2)
    return min(max(score, 0.0), 1.0)


# ═════════════════════════════════════════════════════════════
# 5.  DATA-QUALITY HELPERS
# ═════════════════════════════════════════════════════════════

def coefficient_of_variation(records: List[PriceRecord]) -> float:
    prices = [r.modal_price for r in records if r.modal_price and r.modal_price > 0]
    if len(prices) < 2:
        return 0.0
    mean = statistics.fmean(prices)
    if mean <= 0:
        return 0.0
    return round(statistics.stdev(prices) / mean, 3)


def fresh_records_pct(records: List[PriceRecord],
                      window_days: int = FRESH_RECORD_WINDOW_DAYS) -> Optional[float]:
    """Fraction of records whose arrival_date is within the window."""
    valid = [r for r in records if r.arrival_date]
    if not valid:
        return None
    cutoff = date.today() - timedelta(days=window_days)
    fresh = sum(1 for r in valid if _date_or_min(r.arrival_date) >= cutoff)
    return round(fresh / len(valid) * 100.0, 1)


# ═════════════════════════════════════════════════════════════
# Helpers
# ═════════════════════════════════════════════════════════════

def _date_or_min(s: Optional[str]) -> date:
    """Parse an ISO date string, or return date.min if missing/malformed."""
    if not s:
        return date.min
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(s[:len(fmt) + 4], fmt).date() if "T" in s \
                   else datetime.strptime(s, "%Y-%m-%d").date()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(s).date()
    except ValueError:
        return date.min
