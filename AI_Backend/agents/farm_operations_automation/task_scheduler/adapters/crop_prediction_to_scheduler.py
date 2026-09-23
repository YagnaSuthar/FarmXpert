"""
Adapter — Crop Prediction Agent output → Task Scheduler `crop_selector_agent` block
===================================================================================
Pure-function translator used by the orchestrator. It takes the block the
Crop Prediction agent writes to `crop_recommendation` (or its bare response)
and shapes it into the scheduler's `crop_selector_agent` block.

Design rules:
  • This adapter NEVER mutates the crop-prediction output.
  • The output is a plain dict — the scheduler validates it via Pydantic.
  • `no_suitable_crop`, or any failed run, produces an EMPTY
    `recommended_crops`. The scheduler turns the first recommended crop into
    soil-prep and planting tasks, so anything else here would schedule
    planting on a field the model said nothing suits.
  • Suitability is rescaled 0–100 → 0–10, the scale the scheduler declares.
  • The planting window is the top variety's catalogue sowing window, as
    concrete dates around `today`.
"""

from __future__ import annotations

import calendar
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

_MONTH_INDEX = {name: i for i, name in enumerate(calendar.month_name) if name}


def crop_prediction_output_to_scheduler_block(
    crop_prediction_output: Any,
    *,
    today: Optional[date] = None,
    max_crops: int = 3,
) -> Dict[str, Any]:
    """
    Translate a Crop Prediction output into the scheduler's crop block.

    Parameters
    ----------
    crop_prediction_output
        The orchestrator block `{"agent_status", "result", ...}`, the bare
        response dict, or a `CropPredictionResponse` model.
    today
        Reference date for the planting window. Defaults to today.
    max_crops
        How many ranked crops to pass on. The scheduler acts on the first;
        the rest are context. Three matches the agent's own advice.
    """
    today = today or date.today()
    result = _result_of(crop_prediction_output)

    empty = {"recommended_crops": [], "planting_window_start": None,
             "planting_window_end": None}
    if not result or result.get("status") != "ok":
        return empty

    crops: List[Dict[str, Any]] = []
    for candidate in (result.get("recommendations") or [])[:max_crops]:
        varieties = candidate.get("top_varieties") or []
        top = varieties[0] if varieties else {}
        yield_tha = top.get("expected_yield_tha")
        crops.append({
            "crop_name": candidate.get("crop"),
            # Scheduler scale is 0-10; the agent's suitability is 0-100.
            "suitability_score": round(float(candidate.get("suitability_score") or 0.0) / 10.0, 2),
            "variety": top.get("variety"),
            "duration_days": top.get("duration_days"),
            "expected_yield": f"{yield_tha} t/ha" if yield_tha is not None else None,
            "water_requirement": None,
        })

    if not crops:
        return empty

    first = (result["recommendations"][0].get("top_varieties") or [{}])[0]
    start, end = sowing_window_dates(first.get("sowing_window"), today)
    return {
        "recommended_crops": crops,
        "planting_window_start": start.isoformat() if start else None,
        "planting_window_end": end.isoformat() if end else None,
    }


def sowing_window_dates(window: Optional[str], today: date) -> Tuple[Optional[date], Optional[date]]:
    """'June-July' → the current occurrence if today is inside it, else the next.

    Windows may wrap the year ("November-January"). Returns (None, None) for
    anything unparseable rather than guessing.
    """
    if not window:
        return None, None
    parts = [p.strip() for p in str(window).split("-", 1)]
    start_m = _MONTH_INDEX.get(parts[0])
    end_m = _MONTH_INDEX.get(parts[-1])
    if start_m is None or end_m is None:
        return None, None

    for year in (today.year - 1, today.year, today.year + 1):
        start = date(year, start_m, 1)
        end_year = year if end_m >= start_m else year + 1
        end = date(end_year, end_m, calendar.monthrange(end_year, end_m)[1])
        if end >= today:
            return start, end
    return None, None


def _result_of(output: Any) -> Optional[dict]:
    if output is None:
        return None
    if hasattr(output, "model_dump"):
        output = output.model_dump(mode="json")
    if not isinstance(output, dict):
        return None
    if "agent_status" in output:
        return output.get("result") if output.get("agent_status") == "success" else None
    return output
