"""
Adapters for the existing FarmXpert agents
===========================================
Each function builds an AgentSpec around an agent that already exists. The
agents themselves are untouched: an adapter only translates the orchestration
context into the call that agent expects, and validates what comes back.

Every adapter has the same three parts:
  execute()          - context in, agent's own output out
  validate_output()  - the agent's output, checked and normalised
  build()            - the metadata that tells the engine how to run it

This is the only layer that knows any agent's calling convention. Adding an
agent means adding a file like this one - nothing in the engine changes.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from AI_Backend.orchestration.contracts import (
    AgentSpec,
    Capability,
    Criticality,
    ExecutionContext,
    NormalizedOutput,
    RetryPolicy,
)
from AI_Backend.orchestration.engine import AgentInputError, AgentOutputError

_UTC_NOW = lambda: datetime.now(timezone.utc)  # noqa: E731


# ── Weather Watcher ─────────────────────────────────────────────────────────
# Calls two external providers, so it is the one agent worth retrying: a
# provider blip is transient and a farmer's whole plan depends on the forecast.

def build_weather() -> AgentSpec:
    from AI_Backend.agents.crop_planning_growth.weather_watcher.agent import WeatherAgent
    from AI_Backend.agents.crop_planning_growth.weather_watcher.config import AGENT_VERSION

    agent = WeatherAgent("weather")

    async def execute(context: ExecutionContext) -> Any:
        if not context.location:
            raise AgentInputError("Weather needs a location.")
        return await agent.run(dict(context.location))

    def validate_output(raw: Any) -> NormalizedOutput:
        if not isinstance(raw, dict):
            raise AgentOutputError("Weather did not return an object.")
        status = raw.get("status")
        if status not in (None, "ok", "stale"):
            # The agent reports its own failure in-band rather than raising.
            raise AgentOutputError(f"Weather reported status '{status}'.")
        days = raw.get("forecast_short_term") or raw.get("forecast") or []
        if not days:
            raise AgentOutputError("Weather returned no forecast days.")

        warnings = list(raw.get("warnings") or [])
        age = _seconds_since(raw.get("fetched_at") or raw.get("retrieved_at"))
        if status == "stale":
            warnings.append("The forecast is older than usual; treat it with care.")
        return NormalizedOutput(
            data=raw,
            confidence=_clamp(raw.get("confidence")),
            produced_at=_UTC_NOW(),
            freshness_s=age,
            sources=list(raw.get("sources") or ["open-meteo"]),
            warnings=warnings)

    return AgentSpec(
        name="weather_watcher",
        version=AGENT_VERSION,
        description="Forecast, alerts and agromet advisories for a location.",
        capabilities=frozenset({Capability.WEATHER_FORECAST}),
        requires_context=frozenset({"location"}),
        criticality=Criticality.OPTIONAL,
        timeout_s=12.0,
        retry=RetryPolicy(max_attempts=3, base_delay_s=0.4, max_delay_s=2.0),
        execute=execute,
        validate_output=validate_output,
        input_schema={"type": "object",
                      "properties": {"lat": {"type": "number"}, "lon": {"type": "number"}},
                      "required": ["lat", "lon"]})


# ── Soil Health ─────────────────────────────────────────────────────────────
# Pure computation over sensor or lab readings: no I/O, so no retry and a
# short timeout. It fails only on input it cannot use.

def build_soil() -> AgentSpec:
    from AI_Backend.agents.crop_planning_growth.soil_health.agent import SoilHealthAgent
    from AI_Backend.agents.crop_planning_growth.soil_health.config import AGENT_VERSION

    agent = SoilHealthAgent()

    async def execute(context: ExecutionContext) -> Any:
        if not context.soil:
            raise AgentInputError("Soil health needs at least pH and conductivity.")
        readings = dict(context.soil)
        if context.crop and context.crop.get("name") and "crop_type" not in readings:
            readings["crop_type"] = context.crop["name"]
        return await agent.run(readings)

    def validate_output(raw: Any) -> NormalizedOutput:
        if not isinstance(raw, dict) or not raw:
            raise AgentOutputError("Soil health returned nothing usable.")
        score = raw.get("soil_health_score")
        if score is not None and not 0 <= float(score) <= 100:
            raise AgentOutputError(f"Soil health score {score} is outside 0-100.")
        return NormalizedOutput(
            data=raw,
            confidence=_quality_to_confidence(raw.get("data_quality")),
            produced_at=_UTC_NOW(),
            sources=["soil_sensor" if raw.get("nutrient_source") == "sensor" else "soil_test"],
            warnings=list(raw.get("warnings") or []))

    return AgentSpec(
        name="soil_health",
        version=AGENT_VERSION,
        description="Soil condition, alerts and fertilizer recommendations from readings.",
        capabilities=frozenset({Capability.SOIL_ASSESSMENT}),
        requires_context=frozenset({"soil"}),
        optional_context=frozenset({"crop"}),
        criticality=Criticality.OPTIONAL,
        timeout_s=5.0,
        execute=execute,
        validate_output=validate_output,
        input_schema={"type": "object",
                      "properties": {"soil_ph": {"type": "number"},
                                     "electrical_conductivity": {"type": "number"},
                                     "soil_moisture": {"type": "number"},
                                     "soil_type": {"type": "string"},
                                     "crop_type": {"type": "string"}},
                      "required": ["soil_ph", "electrical_conductivity"]})


# ── Irrigation Planner ──────────────────────────────────────────────────────
# Depends on weather for the water balance. Soil is optional: without it the
# agent still plans, just without salinity and pH adjustments.

def build_irrigation() -> AgentSpec:
    from AI_Backend.agents.crop_planning_growth.irrigation_planner.agent import IrrigationAgent
    from AI_Backend.agents.crop_planning_growth.irrigation_planner.config import AGENT_VERSION

    agent = IrrigationAgent()

    async def execute(context: ExecutionContext) -> Any:
        crop = context.crop or {}
        if not context.location:
            raise AgentInputError("Irrigation planning needs a location.")
        if not crop.get("name"):
            raise AgentInputError("Irrigation planning needs the crop being grown.")

        payload: Dict[str, Any] = {
            "location": dict(context.location),
            "crop": crop["name"],
            "growth_stage": crop.get("growth_stage"),
            "days_after_sowing": crop.get("days_after_sowing"),
            # The planner reads farm_area_hectares; under any other name every
            # farm's water volume was computed for its 1 ha default.
            "farm_area_hectares": crop.get("area_hectares"),
            "soil_type": (context.soil or {}).get("soil_type"),
            "soil_moisture_percent": (context.soil or {}).get("soil_moisture"),
        }
        # Drip needs a fraction of flood's water; without the method every farm
        # would be planned as flood-irrigated. "rainfed" means no system at all.
        method = crop.get("irrigation_method")
        if method and method != "rainfed":
            payload["irrigation_method"] = method
        soil_output = context.output("soil_health")
        if context.soil:
            payload["soil_data"] = dict(context.soil)
        if isinstance(soil_output, dict):
            # Reuse the soil agent's own reading of the field rather than
            # re-deriving it here.
            payload.setdefault("soil_data", {}).update(
                {k: v for k, v in (soil_output.get("readings") or {}).items() if v is not None})
        return await agent.run({k: v for k, v in payload.items() if v is not None})

    def validate_output(raw: Any) -> NormalizedOutput:
        if isinstance(raw, dict) and "irrigation_advice" in raw:
            raw = raw["irrigation_advice"]
        if not isinstance(raw, dict):
            raise AgentOutputError("Irrigation planning returned no plan.")
        if raw.get("status") in {"error", "invalid_input"}:
            raise AgentOutputError(str(raw.get("error", "irrigation planning failed")))
        schedule = raw.get("irrigation_schedule") or raw.get("schedule")
        if schedule is None:
            raise AgentOutputError("Irrigation plan has no schedule.")
        for day in schedule:
            depth = (day or {}).get("water_depth_mm")
            if depth is not None and (float(depth) < 0 or float(depth) > 500):
                raise AgentOutputError(f"Implausible irrigation depth: {depth} mm.")
        return NormalizedOutput(
            data=raw, confidence=_clamp(raw.get("confidence")), produced_at=_UTC_NOW(),
            sources=["fao56_water_balance"], warnings=list(raw.get("warnings") or []))

    return AgentSpec(
        name="irrigation_planner",
        version=AGENT_VERSION,
        description="When and how much to irrigate, from the FAO-56 water balance.",
        capabilities=frozenset({Capability.IRRIGATION_ADVICE}),
        requires_context=frozenset({"location", "crop"}),
        optional_context=frozenset({"soil"}),
        depends_on=frozenset({"weather_watcher"}),
        optional_depends_on=frozenset({"soil_health"}),
        criticality=Criticality.OPTIONAL,
        timeout_s=15.0,
        execute=execute,
        validate_output=validate_output,
        input_schema={"type": "object",
                      "properties": {"lat": {"type": "number"}, "lon": {"type": "number"},
                                     "crop": {"type": "string"},
                                     "growth_stage": {"type": "string"},
                                     "soil_type": {"type": "string"}},
                      "required": ["lat", "lon", "crop"]})


# ── Crop Prediction ─────────────────────────────────────────────────────────
# Reads climate history (cached on disk) and runs a LightGBM model. Slow only
# the first time for a given area, so one retry covers a cold archive fetch.

def build_crop() -> AgentSpec:
    from AI_Backend.agents.crop_planning_growth.crop_prediction.agent import CropPredictionAgent
    from AI_Backend.agents.crop_planning_growth.crop_prediction.config import AGENT_VERSION

    agent = CropPredictionAgent()

    async def execute(context: ExecutionContext) -> Any:
        soil = context.soil or {}
        if not soil.get("soil_ph") and not soil.get("ph"):
            raise AgentInputError("Crop prediction needs soil pH.")
        payload: Dict[str, Any] = {
            "ph": soil.get("ph", soil.get("soil_ph")),
            "ec_ds_m": soil.get("ec_ds_m", soil.get("electrical_conductivity")),
            "moisture_percent": soil.get("moisture_percent", soil.get("soil_moisture")),
            "soil_type": soil.get("soil_type"),
            "region": (context.extras or {}).get("region") or (context.crop or {}).get("region"),
            "month": (context.crop or {}).get("month"),
            "previous_crops": (context.crop or {}).get("previous_crops"),
            "irrigation_available": (context.resources or {}).get("irrigation_available"),
        }
        if context.location:
            payload["location"] = dict(context.location)
        response = await agent.predict({k: v for k, v in payload.items() if v is not None})
        return response.model_dump(mode="json") if hasattr(response, "model_dump") else response

    def validate_output(raw: Any) -> NormalizedOutput:
        if not isinstance(raw, dict):
            raise AgentOutputError("Crop prediction returned no result.")
        block = raw.get("result", raw)
        recommendations = (block or {}).get("recommendations")
        status = raw.get("agent_status") or (block or {}).get("status")
        if status == "no_suitable_crop":
            # A real, meaningful answer: this field suits nothing well now.
            return NormalizedOutput(data=raw, produced_at=_UTC_NOW(),
                                    sources=["crop_model", "era5_climatology"],
                                    warnings=["No crop scored well enough for this field."])
        if not recommendations:
            raise AgentOutputError("Crop prediction returned no recommendations.")
        top = recommendations[0]
        score = top.get("suitability_score", top.get("score"))
        if score is not None and not 0 <= float(score) <= 100:
            raise AgentOutputError(f"Implausible suitability score: {score}.")
        return NormalizedOutput(
            data=raw,
            confidence=_clamp(top.get("confidence")) or _score_to_confidence(score),
            produced_at=_UTC_NOW(),
            sources=["crop_model", "era5_climatology"],
            warnings=list((block or {}).get("warnings") or []))

    return AgentSpec(
        name="crop_predictor",
        version=AGENT_VERSION,
        description="Ranks crops for this field and season from soil, climate and a trained model.",
        capabilities=frozenset({Capability.CROP_SELECTION}),
        requires_context=frozenset({"soil"}),
        optional_context=frozenset({"location", "crop", "resources"}),
        criticality=Criticality.OPTIONAL,
        timeout_s=20.0,
        retry=RetryPolicy(max_attempts=2, base_delay_s=0.5),
        execute=execute,
        validate_output=validate_output,
        input_schema={"type": "object",
                      "properties": {"ph": {"type": "number"},
                                     "ec_ds_m": {"type": "number"},
                                     "soil_type": {"type": "string"},
                                     "region": {"type": "string"},
                                     "month": {"type": "string"}},
                      "required": ["ph"]})


# ── Task Scheduler ──────────────────────────────────────────────────────────
# The one agent that consumes other agents. Everything it depends on is
# optional: a plan from weather alone is still worth showing a farmer.

def build_scheduler() -> AgentSpec:
    from AI_Backend.agents.farm_operations_automation.task_scheduler.agent import TaskSchedulerAgent
    from AI_Backend.agents.farm_operations_automation.task_scheduler.config import AGENT_VERSION

    agent = TaskSchedulerAgent()

    async def execute(context: ExecutionContext) -> Any:
        crop = context.crop or {}
        payload: Dict[str, Any] = {
            "request_id": context.request_id,
            "farm_id": context.farm_id or "farm",
            "field_id": crop.get("field_id") or context.farm_id or "field",
            "current_crop": crop.get("name"),
            "growth_stage": crop.get("growth_stage"),
            "days_to_harvest": crop.get("days_to_harvest"),
            "in_flower": crop.get("in_flower", False),
            "total_area_hectares": crop.get("area_hectares"),
            "resources": context.resources or {},
            "current_timestamp": _UTC_NOW().isoformat(),
        }
        if context.location:
            payload["location"] = dict(context.location)

        # Raw agent outputs; the scheduler's own adapters translate them.
        for key, agent_name in (("weather_data", "weather_watcher"),
                                ("soil_data", "soil_health"),
                                ("irrigation_advice", "irrigation_planner"),
                                ("crop_recommendation", "crop_predictor")):
            produced = context.output(agent_name)
            if produced is not None:
                payload[key] = produced

        if not any(k in payload for k in
                   ("weather_data", "soil_data", "irrigation_advice", "crop_recommendation")):
            raise AgentInputError("Nothing to plan: no other agent produced a result.")
        return await agent.run({k: v for k, v in payload.items() if v is not None})

    def validate_output(raw: Any) -> NormalizedOutput:
        if isinstance(raw, dict) and "task_plan" in raw:
            raw = raw["task_plan"]
        if not isinstance(raw, dict) or "all_tasks" not in raw:
            raise AgentOutputError("Task scheduler returned no plan.")
        counted = (raw.get("total_tasks_scheduled", 0) + raw.get("total_tasks_delayed", 0)
                   + raw.get("total_tasks_skipped", 0))
        if counted != len(raw["all_tasks"]):
            raise AgentOutputError("Task plan counts do not match its task list.")
        return NormalizedOutput(
            data=raw, produced_at=_UTC_NOW(),
            sources=["task_scheduler"], warnings=list(raw.get("warnings") or []))

    return AgentSpec(
        name="task_scheduler",
        version=AGENT_VERSION,
        description="Turns every agent's findings into the farmer's day: what to do, when, and why.",
        capabilities=frozenset({Capability.WORK_PLAN}),
        optional_context=frozenset({"crop", "resources", "location"}),
        optional_depends_on=frozenset({"weather_watcher", "soil_health",
                                       "irrigation_planner", "crop_predictor"}),
        criticality=Criticality.OPTIONAL,
        timeout_s=8.0,
        execute=execute,
        validate_output=validate_output,
        input_schema={"type": "object",
                      "properties": {"farm_id": {"type": "string"},
                                     "current_crop": {"type": "string"},
                                     "growth_stage": {"type": "string"},
                                     "days_to_harvest": {"type": "integer"}}})


# ── Market Intelligence ─────────────────────────────────────────────────────
# Calls a public mandi API that is frequently slow or empty. Best effort: a
# farmer's work plan must not depend on a price server being up.

def build_market() -> AgentSpec:
    from AI_Backend.agents.supplychain_market_access.market_intelligence.agent import run_market_agent
    from AI_Backend.agents.supplychain_market_access.market_intelligence.config import AGENT_VERSION
    from AI_Backend.agents.supplychain_market_access.market_intelligence.schemas import (
        MarketQueryInput,
    )

    async def execute(context: ExecutionContext) -> Any:
        market = context.market or {}
        commodity = market.get("commodity") or (context.crop or {}).get("name")
        if not commodity:
            raise AgentInputError("Market intelligence needs a commodity.")
        query = MarketQueryInput(
            commodity=commodity,
            state=market.get("state"),
            district=market.get("district"),
            forecast_horizon_days=int(market.get("forecast_horizon_days", 7)))
        insights = await run_market_agent(query)
        return insights.model_dump(mode="json") if insights is not None else None

    def validate_output(raw: Any) -> NormalizedOutput:
        if raw is None:
            # A real answer: there is no price data for this commodity today.
            return NormalizedOutput(
                data=None, produced_at=_UTC_NOW(), sources=["data.gov.in"],
                warnings=["No usable mandi price data was available."])
        if not isinstance(raw, dict) or "price_summary" not in raw:
            raise AgentOutputError("Market intelligence returned an unexpected shape.")
        average = (raw.get("price_summary") or {}).get("modal_price_avg")
        if average is not None and (float(average) <= 0 or float(average) > 1_000_000):
            raise AgentOutputError(f"Implausible modal price: {average}.")
        return NormalizedOutput(
            data=raw, confidence=_clamp(raw.get("confidence")), produced_at=_UTC_NOW(),
            freshness_s=_seconds_since(raw.get("processed_at")),
            sources=["data.gov.in"], warnings=[])

    return AgentSpec(
        name="market_intelligence",
        version=AGENT_VERSION,
        description="Mandi prices, trend and short-horizon price forecast for a commodity.",
        capabilities=frozenset({Capability.MARKET_INTELLIGENCE}),
        requires_context=frozenset(),
        optional_context=frozenset({"market", "crop"}),
        criticality=Criticality.BEST_EFFORT,
        timeout_s=15.0,
        retry=RetryPolicy(max_attempts=2, base_delay_s=0.8, max_delay_s=3.0),
        execute=execute,
        validate_output=validate_output,
        input_schema={"type": "object",
                      "properties": {"commodity": {"type": "string"},
                                     "state": {"type": "string"},
                                     "district": {"type": "string"}},
                      "required": ["commodity"]})


# ── helpers ─────────────────────────────────────────────────────────────────

def _clamp(value: Any) -> Optional[float]:
    """A confidence an agent reported, normalised to 0-1, or None."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number):
        return None
    if number > 1.0:            # some agents report percentages
        number /= 100.0
    return max(0.0, min(1.0, number))


def _score_to_confidence(score: Any) -> Optional[float]:
    value = _clamp(score)
    return value


def _quality_to_confidence(quality: Any) -> Optional[float]:
    """Soil health reports data quality rather than confidence."""
    if isinstance(quality, dict):
        return _clamp(quality.get("score") or quality.get("completeness"))
    return _clamp(quality)


def _seconds_since(stamp: Any) -> Optional[float]:
    """Age of a timestamp in seconds. Unknown stays unknown."""
    if not stamp:
        return None
    try:
        moment = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return max(0.0, (_UTC_NOW() - moment).total_seconds())
