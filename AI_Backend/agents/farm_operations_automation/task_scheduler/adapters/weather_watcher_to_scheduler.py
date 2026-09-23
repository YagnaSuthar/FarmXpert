"""
Adapter — Weather Watcher output → Task Scheduler `weather_agent` block
========================================================================
Pure-function translator used by the orchestrator. Maps the dict
returned by WeatherAgent.run() to the `weather_agent` block of the
Task Scheduler's SchedulerInput.

Design rules:
  • Never mutates the upstream weather output.
  • Trims the forecast to the scheduler's planning horizon (today +
    horizon_days) so the scheduler doesn't see far-future days it can't act on.
  • Combines `forecast_short_term` and `forecast_long_term` (preferring
    short-term for overlapping dates — already deduped by the agent).
  • Maps the agent's `wind_speed` (km/h) → scheduler's `wind_speed_kmh`.
  • Maps the agent's `rain_probability_percent` 1:1.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional


def weather_output_to_scheduler_block(
    weather_output: Any,
    *,
    horizon_days: int = 7,
    reference_date: Optional[date] = None,
) -> Dict[str, Any]:
    """
    Translate a Weather Watcher output into the Task Scheduler's `weather_agent` block.

    Parameters
    ----------
    weather_output
        Dict returned by WeatherAgent.run() (or a Pydantic model with .model_dump()).
    horizon_days
        Trim the forecast to today + horizon_days (default 7). The scheduler
        only acts within this window.
    reference_date
        The day to start the horizon from (defaults to today). Pass the same
        date the scheduler's `farm.current_timestamp.date()` resolves to so
        the windows align.

    Returns
    -------
    dict
        Ready to drop into `SchedulerInput.weather_agent`.
    """
    out = _as_dict(weather_output)
    today = reference_date or date.today()
    end   = today + timedelta(days=horizon_days)

    current   = _build_current(out.get("current_weather") or {})
    forecast  = _build_forecast(
        list(out.get("forecast_short_term") or []) +
        list(out.get("forecast_long_term")  or []),
        today, end,
    )
    alerts    = _build_alerts(out.get("alerts") or [], today, end)

    block: Dict[str, Any] = {
        "current":  current,
        "forecast": forecast,
        "alerts":   alerts,
    }
    return block


# ─────────────────────────────────────────────────────────────────────────────
# Builders
# ─────────────────────────────────────────────────────────────────────────────

def _build_current(cw: dict) -> Optional[dict]:
    """Map WeatherAgent's current dict → scheduler WeatherCurrent."""
    if not cw:
        return None
    temp = cw.get("temperature")
    if temp is None:
        return None
    return {
        "temperature_c":      float(temp),
        "humidity_percent":   float(cw.get("humidity", 0.0) or 0.0),
        "wind_speed_kmh":     float(cw.get("wind_speed", 0.0) or 0.0),
        "conditions":         cw.get("conditions"),
        "rainfall_today_mm":  float(cw.get("rainfall_today", 0.0) or 0.0),
    }


def _build_forecast(
    days: Iterable[dict], today: date, end: date,
) -> List[dict]:
    """Sort, dedupe-by-date, and clamp to the planning horizon."""
    by_date: Dict[date, dict] = {}
    for d in days:
        parsed = _parse_date(d.get("date"))
        if parsed is None:
            continue
        if parsed < today or parsed > end:
            continue
        # Keep the first occurrence (short-term comes before long-term in caller).
        by_date.setdefault(parsed, d)

    out: List[dict] = []
    for d in sorted(by_date.keys()):
        src = by_date[d]
        out.append({
            "date":                     d.isoformat(),
            "temp_min_c":               float(src.get("temp_min", 0.0) or 0.0),
            "temp_max_c":               float(src.get("temp_max", 0.0) or 0.0),
            "rainfall_mm":              float(src.get("rainfall_mm", 0.0) or 0.0),
            "rain_probability_percent": float(src.get("rain_probability_percent", 0.0) or 0.0),
            "wind_speed_kmh":           float(src.get("wind_speed", 0.0) or 0.0),
            "humidity_percent":         _maybe_float(src.get("humidity")),
            "storm_warning":            bool(src.get("storm_warning", False)),
            "frost_risk":               bool(src.get("frost_risk", False)),
            "heat_stress_risk":         bool(src.get("heat_stress_risk", False)),
        })
    return out


def _build_alerts(alerts: Iterable[dict], today: date, end: date) -> List[dict]:
    """Pass through, normalising shape & clamping dated alerts to horizon."""
    out: List[dict] = []
    for a in alerts:
        d = _parse_date(a.get("date"))
        if d is not None and (d < today or d > end):
            continue
        out.append({
            "type":     a.get("type") or "unknown",
            "severity": _normalise_severity(a.get("severity")),
            "message":  a.get("message") or "",
            "date":     d.isoformat() if d else None,
            "recommendations": list(a.get("recommendations") or []),
        })
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

_VALID_SEVERITIES = {"low", "medium", "high", "critical"}


def _as_dict(payload: Any) -> Dict[str, Any]:
    if payload is None:
        return {}
    if hasattr(payload, "model_dump"):
        return payload.model_dump()
    if isinstance(payload, dict):
        return payload
    raise TypeError(
        "weather_output_to_scheduler_block expects a dict or Pydantic model; "
        f"got {type(payload).__name__}."
    )


def _parse_date(v: Any) -> Optional[date]:
    if v is None:
        return None
    if isinstance(v, date) and not isinstance(v, datetime):
        return v
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, str):
        try:
            return datetime.strptime(v, "%Y-%m-%d").date()
        except ValueError:
            try:
                return datetime.fromisoformat(v).date()
            except ValueError:
                return None
    return None


def _normalise_severity(sev: Any) -> str:
    s = str(sev or "medium").lower().strip()
    return s if s in _VALID_SEVERITIES else "medium"


def _maybe_float(v: Any) -> Optional[float]:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None
