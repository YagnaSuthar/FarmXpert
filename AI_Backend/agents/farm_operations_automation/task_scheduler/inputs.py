"""
Task Scheduler Agent — Input normalisation
===========================================
Accepts what the caller actually has and shapes it into a SchedulerInput.

Three shapes arrive in practice:

  1. a payload already in SchedulerInput shape (the API);
  2. orchestrator state holding each specialist agent's raw output under
     its own key (`weather_data`, `soil_data`, `irrigation_advice`,
     `crop_recommendation`, `pest_disease`);
  3. a mixture - a farm block plus one or two raw agent outputs.

Raw outputs are converted by the orchestrator's adapters, which are the
single place that knows each agent's output shape. They are imported
lazily so this package never depends on the orchestrator at import time.

Missing pieces are filled with safe defaults rather than rejected: a plan
built from the weather alone is still worth showing a farmer.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from AI_Backend.agents.farm_operations_automation.task_scheduler.config import (
    DEFAULT_HORIZON_DAYS,
    DEFAULT_WORK_END,
    DEFAULT_WORK_START,
    MAX_HORIZON_DAYS,
)

logger = logging.getLogger("farmxpert.task_scheduler")

# Where each specialist agent's raw output is found in orchestrator state,
# and the scheduler block it feeds.
RAW_SOURCES = {
    "weather_data":        "weather_agent",
    "soil_data":           "soil_health_agent",
    "soil_analysis":       "soil_health_agent",
    "irrigation_advice":   "irrigation_agent",
    "crop_recommendation": "crop_selector_agent",
    "market_insights":     "market_intelligence_agent",
    "pest_disease":        "pest_disease_agent",
}

BLOCK_KEYS = ("weather_agent", "irrigation_agent", "soil_health_agent",
              "crop_selector_agent", "market_intelligence_agent", "pest_disease_agent")


def normalise(payload: Any) -> Dict[str, Any]:
    """Return a dict SchedulerInput can validate."""
    data = _as_dict(payload)
    if not isinstance(data, dict):
        raise TypeError("Task scheduler input must be a mapping.")

    out: Dict[str, Any] = {
        "request_id": str(data.get("request_id") or uuid.uuid4().hex),
        "farm": _farm(data),
        "resources": _resources(data.get("resources")),
        "planning_horizon_days": _horizon(data.get("planning_horizon_days")),
    }

    for key in BLOCK_KEYS:
        block = data.get(key)
        if block:
            out[key] = _as_dict(block)

    horizon = out["planning_horizon_days"]
    reference = out["farm"]["current_timestamp"]
    reference_date = reference.date() if isinstance(reference, datetime) else None
    area = out["farm"].get("total_area_hectares") or 1.0

    for raw_key, block_key in RAW_SOURCES.items():
        raw = data.get(raw_key)
        if not raw or block_key in out:
            continue
        converted = _convert(block_key, raw, horizon, reference_date, area)
        if converted:
            out[block_key] = converted

    return out


def _convert(block_key: str, raw: Any, horizon: int,
             reference_date, area: float) -> Optional[dict]:
    """Run the matching orchestrator adapter. A failure here loses one
    agent's contribution, never the whole plan."""
    try:
        from AI_Backend.agents.farm_operations_automation.task_scheduler import adapters
    except ImportError:  # pragma: no cover - orchestrator not installed
        logger.warning("Orchestrator adapters unavailable; raw agent output ignored.")
        return None

    try:
        if block_key == "weather_agent":
            return adapters.weather_output_to_scheduler_block(
                raw, horizon_days=horizon, reference_date=reference_date)
        if block_key == "soil_health_agent":
            return adapters.soil_health_output_to_scheduler_block(raw)
        if block_key == "irrigation_agent":
            return adapters.irrigation_output_to_scheduler_block(
                raw, horizon_days=horizon, reference_date=reference_date,
                farm_area_hectares=area)
        if block_key == "crop_selector_agent":
            return adapters.crop_prediction_output_to_scheduler_block(raw)
        if block_key == "market_intelligence_agent":
            return adapters.market_insights_to_scheduler_block(raw)
        if block_key == "pest_disease_agent":
            return _as_dict(raw)
    except Exception as exc:  # noqa: BLE001 - one agent must not break the plan
        logger.warning("Could not use %s output: %s", block_key, exc)
    return None


def _farm(data: Dict[str, Any]) -> Dict[str, Any]:
    farm = _as_dict(data.get("farm")) or {}
    farm = dict(farm)

    # Orchestrator state often carries these at the top level.
    for key in ("farm_id", "field_id", "current_crop", "growth_stage",
                "total_area_hectares", "days_to_harvest", "soil_type", "timezone"):
        if key not in farm and data.get(key) is not None:
            farm[key] = data[key]

    farm.setdefault("farm_id", "farm")
    farm.setdefault("field_id", farm["farm_id"])

    location = farm.get("location") or data.get("location")
    if isinstance(location, dict) and {"lat", "lon"} <= set(location):
        farm["location"] = {"lat": location["lat"], "lon": location["lon"]}
    else:
        farm.pop("location", None)

    stamp = farm.get("current_timestamp") or data.get("current_timestamp")
    farm["current_timestamp"] = _timestamp(stamp)
    return farm


def _timestamp(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            logger.warning("Unreadable timestamp %r - planning from now instead.", value)
    return datetime.now(timezone.utc)


def _resources(value: Any) -> Dict[str, Any]:
    res = dict(_as_dict(value) or {})
    res.setdefault("working_hours_start", DEFAULT_WORK_START)
    res.setdefault("working_hours_end", DEFAULT_WORK_END)
    # A farm with no equipment listed is not a farm with no equipment - it is
    # a farm nobody asked. An empty list disables the equipment check.
    res.setdefault("equipment_available", [])
    return res


def _horizon(value: Any) -> int:
    try:
        days = int(value)
    except (TypeError, ValueError):
        return DEFAULT_HORIZON_DAYS
    return max(1, min(MAX_HORIZON_DAYS, days))


def _as_dict(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if hasattr(value, "dict"):
        try:
            return value.dict()
        except TypeError:
            pass
    return value
