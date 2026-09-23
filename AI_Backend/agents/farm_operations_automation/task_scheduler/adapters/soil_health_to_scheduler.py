"""
Adapter — Soil Health Agent output → Task Scheduler `soil_health_agent` block
=============================================================================
Pure-function translator used by the orchestrator. It takes the dict
returned by SoilHealthAgent.run() (matching schemas.SoilHealthOutput)
and shapes it into the `soil_health_agent` block of the Task Scheduler's
SchedulerInput.

Design rules:
  • This adapter NEVER mutates the soil-health output.
  • The soil-health agent's own input/output stays untouched.
  • The output of this adapter is a plain dict — the scheduler validates
    it via Pydantic, so we keep this side dependency-free.
  • Severity normalisation: "info" is dropped (scheduler treats info as
    non-actionable noise); "critical" is preserved as-is.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional


# Severities that are surfaced to the scheduler; "info" alerts are noise
# at the scheduler level (sensor jitter) and would only inflate task count.
_SURFACED_SEVERITIES = {"low", "medium", "high", "critical"}


def soil_health_output_to_scheduler_block(
    soil_health_output: Any,
    *,
    include_low_severity: bool = True,
    surface_weather_alerts: bool = False,
) -> Dict[str, Any]:
    """
    Translate a Soil Health Agent output into the Task Scheduler's
    `soil_health_agent` block.

    Parameters
    ----------
    soil_health_output
        Either the dict returned by SoilHealthAgent.run() or a Pydantic
        SoilHealthOutput model.
    include_low_severity
        If False, alerts of severity 'low' are dropped before being passed
        downstream. Useful when the orchestrator wants the scheduler to
        focus on actionable problems only.
    surface_weather_alerts
        Soil Health emits a separate `weather_alerts` list. By default we
        leave those for the Weather Watcher block — set True to merge them
        into the soil block instead (useful if the weather agent is offline).

    Returns
    -------
    dict
        Ready to drop directly into `SchedulerInput.soil_health_agent`.
    """
    out = _as_dict(soil_health_output)

    soil_alerts    = list(out.get("soil_alerts") or [])
    weather_alerts = list(out.get("weather_alerts") or [])
    raw_alerts: Iterable[dict] = soil_alerts + (weather_alerts if surface_weather_alerts else [])

    return {
        "soil_health_score":  out.get("soil_health_score"),
        "soil_health_status": out.get("soil_health_status"),
        "summary":            out.get("summary"),
        "critical_factors":   list(out.get("critical_factors") or []),

        "alerts": [
            {
                "type":     a.get("type", "UNKNOWN"),
                "message":  a.get("message", ""),
                "severity": _normalise_severity(a.get("severity")),
            }
            for a in raw_alerts
            if _keep_alert(a, include_low_severity)
        ],

        "fertilizers": [
            {
                "fertilizer":   f.get("fertilizer", ""),
                "display_name": f.get("display_name", f.get("fertilizer", "")),
                "dosage":       f.get("dosage", "—"),
                "timing":       f.get("timing", "—"),
                "method":       f.get("method", "—"),
                "triggered_by": f.get("triggered_by"),
                "cautions":     list(f.get("cautions") or []),
            }
            for f in (out.get("fertilizers") or [])
            if _is_actionable_fertilizer(f)
        ],
    }


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _as_dict(payload: Any) -> Dict[str, Any]:
    """Coerce a Pydantic model or dict to a plain dict (idempotent)."""
    if payload is None:
        return {}
    if hasattr(payload, "model_dump"):
        return payload.model_dump()
    if isinstance(payload, dict):
        return payload
    raise TypeError(
        "soil_health_output_to_scheduler_block expects a dict or Pydantic model; "
        f"got {type(payload).__name__}."
    )


def _normalise_severity(sev: Optional[str]) -> str:
    """Drop unknown labels; scheduler expects low|medium|high|critical."""
    if not sev:
        return "medium"
    s = str(sev).lower().strip()
    if s in _SURFACED_SEVERITIES:
        return s
    if s == "info":
        return "low"
    return "medium"


def _keep_alert(alert: dict, include_low_severity: bool) -> bool:
    sev = _normalise_severity(alert.get("severity"))
    if sev == "low" and not include_low_severity:
        return False
    # Soft alerts (10 % tolerance buffer hits) are not actionable on their own.
    if alert.get("soft_alert"):
        return include_low_severity
    return True


def _is_actionable_fertilizer(fert: dict) -> bool:
    """Drop 'none' / withhold entries — they don't become scheduler tasks."""
    key = (fert.get("fertilizer") or "").strip().lower()
    if not key or key == "none":
        return False
    if (fert.get("method") or "").strip().lower() == "withhold":
        return False
    return True
