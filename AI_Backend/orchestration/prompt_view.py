"""
Prompt view — what the language model actually needs to see
============================================================
The cheapest token is the one never sent.

Agent outputs are built for the API and the dashboard: they carry diagnostics,
model versions, data-quality blocks, per-day intermediate values and the full
reasoning trace. All of that is worth returning to a client, and almost none
of it belongs in a prompt whose only job is to phrase an answer for a farmer.

So before encoding anything, the results are projected down to the facts the
answer depends on: the decisions, the numbers a farmer acts on, the advice,
and the warnings. This is a far larger saving than any choice of format -
selection is first-order, encoding is second-order.

Two rules:

  * Projection SELECTS, it never summarises, rounds or rewrites. Every value
    that survives is byte-identical to what the agent produced, because the
    model is instructed to copy numbers exactly and must not be handed an
    altered one.
  * An unknown agent is passed through with only obvious noise removed. A new
    agent therefore works immediately - at worst it costs more tokens than it
    needs to, which is a tuning problem, not a correctness one.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

# Keys that never help a model write a farmer's answer, whatever agent they
# come from: provenance of the computation rather than the advice itself.
NOISE_KEYS = frozenset({
    "agent_id", "agent_version", "model_version", "processed_at", "request_id",
    "debug", "diagnostics", "data_quality", "raw", "trace", "metadata",
    "execution_time_ms", "cache_hit", "schema_version", "source_urls",
})

MAX_LIST = 8          # a farmer acts on the next few days, not the next fourteen


def project(results: Dict[str, Any]) -> Dict[str, Any]:
    """Reduce every agent result to the facts the answer needs."""
    out: Dict[str, Any] = {}
    for name, payload in results.items():
        if payload is None:
            continue
        projector = _PROJECTORS.get(name, _generic)
        try:
            view = projector(payload)
        except Exception:  # noqa: BLE001 - a projection bug must not lose the answer
            view = _generic(payload)
        if view:
            out[name] = view
    return out


# ── per-agent projections ───────────────────────────────────────────────────

def _weather(payload: Any) -> Any:
    """The next few days and any alert. Hourly detail is for the app."""
    if not isinstance(payload, dict):
        return payload
    days = payload.get("forecast_short_term") or payload.get("forecast") or []
    view: Dict[str, Any] = {
        "forecast": [_pick(day, ("date", "temp_min_c", "temp_max_c", "rainfall_mm",
                                 "rain_probability_percent", "wind_speed_kmh",
                                 "humidity_percent"))
                     for day in days[:5]],
    }
    alerts = payload.get("alerts") or []
    if alerts:
        view["alerts"] = [_pick(a, ("type", "severity", "message", "date"))
                          for a in alerts[:4]]
    advisory = payload.get("agro_advisory") or {}
    if isinstance(advisory, dict):
        summary = advisory.get("summary") or advisory.get("lines")
        if summary:
            view["advisory"] = summary[:6] if isinstance(summary, list) else summary
        windows = advisory.get("spray_windows")
        if windows:
            view["spray_windows"] = windows[:4]
    if payload.get("status") == "stale":
        view["note"] = "forecast is older than usual"
    return view


def _soil(payload: Any) -> Any:
    if not isinstance(payload, dict):
        return payload
    view = _pick(payload, ("soil_health_score", "soil_health_status", "summary"))
    alerts = payload.get("alerts") or payload.get("soil_alerts") or []
    if alerts:
        view["alerts"] = [_pick(a, ("type", "severity", "message")) for a in alerts[:6]]
    fertilizers = payload.get("fertilizers") or []
    if fertilizers:
        view["fertilizers"] = [_pick(f, ("display_name", "dosage", "timing", "method"))
                               for f in fertilizers[:4]]
    moisture = payload.get("moisture_status")
    if moisture:
        view["moisture"] = _pick(moisture, ("status", "available_water_percent")) \
            if isinstance(moisture, dict) else moisture
    return view


def _irrigation(payload: Any) -> Any:
    """The decision, the depth, the timing, and why - not the water balance."""
    if not isinstance(payload, dict):
        return payload
    schedule = payload.get("irrigation_schedule") or payload.get("schedule") or []
    days: List[Dict[str, Any]] = []
    for day in schedule[:MAX_LIST]:
        if not isinstance(day, dict):
            continue
        entry = _pick(day, ("date", "decision", "decision_code", "irrigation_required",
                            "water_depth_mm", "duration_hours", "timing", "method",
                            "farmer_message"))
        # The reason codes are the justification a farmer is owed; keep the
        # codes, drop the intermediate numbers that produced them.
        reasons = day.get("reasons") or []
        if reasons:
            entry["reasons"] = [r.get("code") for r in reasons
                                if isinstance(r, dict) and r.get("code")][:4]
        days.append(entry)
    view: Dict[str, Any] = {"schedule": days}
    for key in ("method_advice", "salinity_advice", "water_savings"):
        if payload.get(key):
            view[key] = payload[key]
    if payload.get("warnings"):
        view["warnings"] = payload["warnings"][:4]
    return view


def _crop(payload: Any) -> Any:
    """The top few crops with the numbers behind the ranking."""
    if not isinstance(payload, dict):
        return payload
    block = payload.get("result") if isinstance(payload.get("result"), dict) else payload
    recommendations = (block or {}).get("recommendations") or []
    view: Dict[str, Any] = {
        "recommendations": [
            {**_pick(rec, ("crop", "crop_name", "suitability_score", "confidence",
                           "season", "expected_yield")),
             **_varieties(rec), **_water(rec)}
            for rec in recommendations[:3]],
    }
    status = payload.get("agent_status") or (block or {}).get("status")
    if status and status != "ok":
        view["status"] = status
    if (block or {}).get("warnings"):
        view["warnings"] = block["warnings"][:3]
    return view


def _varieties(rec: Dict[str, Any]) -> Dict[str, Any]:
    varieties = rec.get("top_varieties") or rec.get("varieties") or []
    if not varieties:
        return {}
    return {"varieties": [_pick(v, ("name", "duration_days", "sowing_window"))
                          for v in varieties[:2]]}


def _water(rec: Dict[str, Any]) -> Dict[str, Any]:
    security = rec.get("water_security")
    if not isinstance(security, dict):
        return {}
    return {"water": _pick(security, ("category", "rain_met_percent_median",
                                      "typical_irrigation_mm"))}


def _scheduler(payload: Any) -> Any:
    """The day itself: what to do, when, why, and what not to do.

    `daily_plans` is dropped because it repeats every task already in
    `all_tasks` - sending both doubles the cost for no extra fact.
    """
    if not isinstance(payload, dict):
        return payload
    view: Dict[str, Any] = _pick(payload, ("headline", "do_first", "summary"))
    tasks = payload.get("all_tasks") or []
    view["tasks"] = [
        {**_pick(task, ("title", "category", "status", "priority", "scheduled_date",
                        "scheduled_start_time", "duration_minutes", "why_now",
                        "cost_of_delay")),
         **_advice(task)}
        for task in tasks[:MAX_LIST]]
    if payload.get("refused_tasks"):
        view["refused"] = [_pick(r, ("title", "rule", "explanation",
                                     "what_to_do_instead"))
                           for r in payload["refused_tasks"]]
    if payload.get("warnings"):
        view["warnings"] = payload["warnings"][:4]
    return view


def _advice(task: Dict[str, Any]) -> Dict[str, Any]:
    """Two of each. A farmer acts on the first points, not on all twelve."""
    out: Dict[str, Any] = {}
    for key in ("do", "do_not", "safety"):
        items = task.get(key)
        if items:
            out[key] = items[:2]
    if task.get("blocked_by"):
        out["blocked_by"] = task["blocked_by"][:2]
    return out


def _market(payload: Any) -> Any:
    if not isinstance(payload, dict):
        return payload
    view = _pick(payload, ("commodity", "confidence"))
    for key in ("price_summary", "price_trend", "forecast"):
        block = payload.get(key)
        if isinstance(block, dict):
            view[key] = _pick(block, ("modal_price_avg", "modal_price_min",
                                      "modal_price_max", "price_unit", "direction",
                                      "predicted_price", "predicted_trend",
                                      "expected_change_pct", "horizon_days"))
    return view


def _retrieval(payload: Any) -> Any:
    """The retrieved text itself, which is the whole point, plus its source."""
    if not isinstance(payload, dict):
        return payload
    return {"passages": [_pick(p, ("title", "text", "doc_id"))
                         for p in (payload.get("passages") or [])[:4]],
            "sources": payload.get("sources") or []}


_PROJECTORS: Dict[str, Callable[[Any], Any]] = {
    "weather_watcher": _weather,
    "soil_health": _soil,
    "irrigation_planner": _irrigation,
    "crop_predictor": _crop,
    "task_scheduler": _scheduler,
    "market_intelligence": _market,
    "retrieval_agent": _retrieval,
}


# ── fallback ────────────────────────────────────────────────────────────────

def _generic(payload: Any, _depth: int = 0) -> Any:
    """An agent with no projector: keep everything except obvious noise.

    New agents work on day one. Tuning one is a later, optional improvement.
    """
    if _depth > 6 or not isinstance(payload, dict):
        return payload
    out: Dict[str, Any] = {}
    for key, value in payload.items():
        if key in NOISE_KEYS or value is None or value == [] or value == {}:
            continue
        if isinstance(value, list):
            out[key] = [_generic(v, _depth + 1) for v in value[:MAX_LIST]]
        elif isinstance(value, dict):
            out[key] = _generic(value, _depth + 1)
        else:
            out[key] = value
    return out


def _pick(source: Any, keys) -> Dict[str, Any]:
    """The named keys that are actually present and non-empty."""
    if not isinstance(source, dict):
        return {}
    return {key: source[key] for key in keys
            if source.get(key) is not None and source.get(key) != ""}
