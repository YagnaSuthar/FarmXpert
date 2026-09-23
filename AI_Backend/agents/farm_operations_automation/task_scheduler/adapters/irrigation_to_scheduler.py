"""
Adapter — Irrigation Planner output → Task Scheduler `irrigation_agent` block
==============================================================================
Pure-function translator the orchestrator uses to plug the irrigation
plan into the Task Scheduler. The irrigation agent's own output is
not modified.

Mapping:
    irrigation_schedule[i] (rich, with decision_code + reasons)
        ↓  drop skip/postpone days; emit only IRRIGATE / EMERGENCY / MAINTAIN_FLOOD
    SchedulerInput.irrigation_agent.schedule[i]
        date / irrigation_required / water_depth_mm / duration_hours /
        water_volume_liters / timing / method / reason
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional


# Decisions that produce an actionable scheduler task.
_ACTIONABLE_DECISIONS = {"IRRIGATE", "EMERGENCY_IRRIGATE", "MAINTAIN_FLOOD"}


def irrigation_output_to_scheduler_block(
    irrigation_output: Any,
    *,
    horizon_days: int = 7,
    reference_date: Optional[date] = None,
    farm_area_hectares: float = 1.0,
) -> Dict[str, Any]:
    """
    Translate an Irrigation Planner output into the Task Scheduler's
    `irrigation_agent` block.

    Parameters
    ----------
    irrigation_output
        Dict returned by IrrigationAgent.run() (or a Pydantic model).
    horizon_days
        Trim schedule to today..today+horizon_days. Default 7.
    reference_date
        Anchor date (defaults to today). Pass the scheduler's farm date
        so the windows align exactly.
    farm_area_hectares
        Used to compute water_volume_liters if missing. 1 ha × 1 mm = 10_000 L.
    """
    out = _as_dict(irrigation_output)
    today = reference_date or date.today()
    end   = today + timedelta(days=horizon_days)
    area_m2 = float(farm_area_hectares) * 10_000.0

    schedule_in  = out.get("irrigation_schedule") or []
    schedule_out = _build_schedule(schedule_in, today, end, area_m2)

    soil_pct = _resolve_current_moisture_pct(out)

    savings_pct = (out.get("water_savings") or {}).get("savings_percentage")
    # Scheduler treats savings as non-negative. Negative savings happen on
    # emergency / very-dry days where optimal honestly exceeds the baseline —
    # not a "savings" the farmer can claim, so clamp at 0 for the scheduler.
    if savings_pct is not None:
        savings_pct = max(0.0, float(savings_pct))

    return {
        "schedule":                       schedule_out,
        "soil_moisture_current_percent":  soil_pct,
        "water_savings_percent":          savings_pct,
        "alerts":                          _build_alerts(out.get("alerts") or [], today, end),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Builders
# ─────────────────────────────────────────────────────────────────────────────

def _build_schedule(
    items: List[dict], today: date, end: date, area_m2: float,
) -> List[dict]:
    """Keep only actionable, in-horizon irrigation days; map to scheduler shape."""
    out: List[dict] = []
    for item in items:
        d = _parse_date(item.get("date"))
        if d is None or d < today or d > end:
            continue

        decision = (item.get("decision_code") or "").upper()
        irrigation_required = bool(item.get("irrigation_required"))
        if decision not in _ACTIONABLE_DECISIONS and not irrigation_required:
            # Skip / postpone days are operational decisions the scheduler
            # doesn't need to slot. They remain visible in the raw output.
            continue

        water_depth_mm = _maybe_float(item.get("water_depth_mm"))
        volume_l = (
            _maybe_float(item.get("water_volume_liters"))
            or (water_depth_mm * area_m2 if water_depth_mm else None)
        )

        out.append({
            "date":                d.isoformat(),
            "irrigation_required": True,
            "water_depth_mm":      water_depth_mm,
            "duration_hours":      _maybe_float(item.get("duration_hours")),
            "water_volume_liters": volume_l,
            "timing":              _normalise_timing(item.get("timing")),
            "method":              (item.get("method") or "drip").lower(),
            "reason":              _build_reason_text(item),
        })
    return out


def _build_alerts(alerts: List[dict], today: date, end: date) -> List[dict]:
    """Pass alerts through. Clamp dated alerts to horizon."""
    out: List[dict] = []
    for a in alerts:
        d = _parse_date(a.get("date"))
        if d is not None and (d < today or d > end):
            continue
        out.append({
            "type": a.get("type", "warning"),
            "severity": (a.get("severity") or "medium").lower(),
            "message":  a.get("message", ""),
            "date":     d.isoformat() if d else None,
            "recommendation": a.get("recommendation"),
        })
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _build_reason_text(item: dict) -> str:
    """
    Compose a concise reason string from the rich `reasons[]` list +
    the agent's `recommendation`. Orchestrator can override with prose.
    """
    rec = item.get("recommendation")
    if rec:
        return rec
    parts: List[str] = []
    for r in (item.get("reasons") or [])[:2]:
        code = r.get("code", "")
        val  = r.get("value")
        thr  = r.get("threshold")
        unit = r.get("unit") or ""
        if val is not None and thr is not None:
            parts.append(f"{code} (value={val}{unit}, threshold={thr}{unit})")
        else:
            parts.append(code)
    return "; ".join(parts) or "Scheduled irrigation."


def _resolve_current_moisture_pct(out: dict) -> Optional[float]:
    """
    Derive current root-zone moisture as % of FC from the first scheduled day,
    so the scheduler can use it for urgency scoring.
    """
    schedule = out.get("irrigation_schedule") or []
    if not schedule:
        return None
    first = schedule[0]
    wb = first.get("water_balance_mm") or {}
    fc = (out.get("crop_profile") or {}).get("field_capacity_mm")
    moisture_before = wb.get("moisture_before")
    if fc and moisture_before is not None and fc > 0:
        return round((moisture_before / fc) * 100.0, 1)
    return None


def _as_dict(payload: Any) -> Dict[str, Any]:
    if payload is None:                    return {}
    if hasattr(payload, "model_dump"):     return payload.model_dump()
    if isinstance(payload, dict):          return payload
    raise TypeError(
        "irrigation_output_to_scheduler_block expects dict or Pydantic model; "
        f"got {type(payload).__name__}."
    )


def _parse_date(v: Any) -> Optional[date]:
    if v is None:                                       return None
    if isinstance(v, date) and not isinstance(v, datetime): return v
    if isinstance(v, datetime):                          return v.date()
    if isinstance(v, str):
        for parser in (
            lambda s: datetime.strptime(s, "%Y-%m-%d").date(),
            lambda s: datetime.fromisoformat(s).date(),
        ):
            try: return parser(v)
            except ValueError: continue
    return None


def _maybe_float(v: Any) -> Optional[float]:
    if v is None: return None
    try: return float(v)
    except (TypeError, ValueError): return None


def _normalise_timing(v: Any) -> Optional[str]:
    """
    Accept the agent's `timing` enum and scheduler-readable strings.

    Agent emits: early_morning | late_morning | evening | night.
    Scheduler accepts free text but prefers 'morning' / 'evening' for slotting.
    """
    if not v:
        return None
    s = str(v).lower().strip()
    if s in {"early_morning", "morning", "late_morning"}: return "morning"
    if s in {"evening", "afternoon"}:                     return "evening"
    if s == "night":                                      return "evening"   # closest available slot
    return s
