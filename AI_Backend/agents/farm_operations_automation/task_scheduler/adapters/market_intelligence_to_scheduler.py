"""
Adapter — Market Intelligence output → Task Scheduler `market_intelligence_agent` block
========================================================================================
Pure-function translator used by the orchestrator.

IMPORTANT — by design, this adapter never sets `recommended_action`. The
market intelligence agent is **insights-only** in v3.0; the scheduler
therefore emits NO market_action task from this block. The block carries
prices and forecast values purely as context so the orchestrator can put
them into the farmer-facing narrative the scheduler produces.

If you ever need to drive a scheduler task from market data, set
`recommended_action` on the dict returned by this adapter before passing
it to SchedulerInput.
"""

from __future__ import annotations

from typing import Any, Dict


def market_insights_to_scheduler_block(market_insights: Any) -> Dict[str, Any]:
    """
    Translate a MarketInsights object into the Task Scheduler's
    `market_intelligence_agent` block.

    Parameters
    ----------
    market_insights
        Either a MarketInsights Pydantic model or a dict in the same shape.

    Returns
    -------
    dict
        Drop directly into `SchedulerInput.market_intelligence_agent`.
        `recommended_action` is intentionally omitted (insights-only).
    """
    out = _as_dict(market_insights)
    summary  = out.get("price_summary")  or {}
    forecast = out.get("forecast")       or {}
    trend    = out.get("price_trend")    or {}

    return {
        "commodity": out.get("commodity") or "",
        "current_modal_price_per_quintal": _maybe_float(summary.get("modal_price_avg")),
        "predicted_price_per_quintal":     _maybe_float(forecast.get("predicted_price")),
        "predicted_trend":                 forecast.get("predicted_trend"),
        "historical_trend":                trend.get("direction"),
        "confidence":                      _maybe_float(out.get("confidence")),
        # Intentionally omitted: recommended_action, reason.
    }


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _as_dict(payload: Any) -> Dict[str, Any]:
    if payload is None:                return {}
    if hasattr(payload, "model_dump"): return payload.model_dump()
    if isinstance(payload, dict):      return payload
    raise TypeError(
        "market_insights_to_scheduler_block expects dict or Pydantic model; "
        f"got {type(payload).__name__}."
    )


def _maybe_float(v: Any):
    if v is None: return None
    try: return float(v)
    except (TypeError, ValueError): return None
