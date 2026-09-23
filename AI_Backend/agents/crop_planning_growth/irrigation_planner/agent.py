"""
IrrigationAgent — FAO-56 irrigation planning for one field.

Accepts:
  • an `IrrigationRequest` or equivalent dict (router, direct calls)
  • orchestrator state: `lat`/`lon`, raw readings under `soil_data`, and
    optionally `weather_data` / `soil_health_data` from agents that already ran
  • a `farm` block carrying location / crop / growth stage

`run()` returns the plan and raises ValueError for unusable input (the router
maps it to 422). As a LangGraph node (`__call__`) it never raises: the plan -
or an error block - is written to `irrigation_advice`, the key FarmState
declares. LangGraph silently drops any key a node returns that is not in the
state schema.
"""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from AI_Backend.agents.base.base_agent import BaseAgent
from AI_Backend.agents.crop_planning_growth.irrigation_planner.config import (
    AGENT_ID,
    AGENT_VERSION,
)
from AI_Backend.agents.crop_planning_growth.irrigation_planner.schemas import (
    IrrigationPlannerResponse,
    IrrigationRequest,
)
from AI_Backend.agents.crop_planning_growth.irrigation_planner.service import (
    IrrigationService,
)

# Inputs that are not part of the request model but pass through to the service.
_PASS_THROUGH = ("weather_data", "soil_health_data", "field_capacity", "wilting_point")


class IrrigationAgent(BaseAgent):
    AGENT_ID = AGENT_ID
    AGENT_VERSION = AGENT_VERSION

    def __init__(self) -> None:
        super().__init__("Irrigation_Planner")
        self.service = IrrigationService(logger=self.logger)

    async def __call__(self, state: Any) -> dict:
        """LangGraph node: never raises, writes to `irrigation_advice`."""
        try:
            plan = await self.run(state)
            return {"irrigation_advice": plan}
        except ValueError as exc:
            self.logger.warning("Irrigation input unusable: %s", exc)
            return {"irrigation_advice": {"status": "invalid_input", "error": str(exc)}}
        except Exception as exc:  # noqa: BLE001
            self.logger.exception("Irrigation planning failed: %s", exc)
            return {"irrigation_advice": {"status": "error", "error": str(exc)}}

    async def run(self, input_data: Any) -> dict:
        payload = self._normalise_input(input_data)
        raw = await self.service.calculate_irrigation_schedule(input_data=payload)
        try:
            plan = IrrigationPlannerResponse.model_validate(raw).model_dump()
        except ValidationError as exc:
            # Output drift is a bug in this agent, not the caller's input.
            self.logger.error("Plan failed its own schema: %s", exc)
            raise RuntimeError("Irrigation plan failed schema validation.") from exc
        self.logger.info(
            "Plan ready | crop=%s stage=%s soil=%s irrigation_days=%d status=%s",
            plan["crop_profile"]["crop"], plan["crop_profile"]["growth_stage"],
            plan["crop_profile"]["soil_type"], plan["summary"]["irrigation_days"],
            plan["status"])
        return self.postprocess(plan)

    # ─────────────────────────────────────────────────────────────────────

    @staticmethod
    def _normalise_input(input_data: Any) -> dict:
        """Coerce every accepted shape into a validated flat payload."""
        if input_data is None:
            raise ValueError("Irrigation planning needs input: at least a location or weather data.")
        if hasattr(input_data, "model_dump"):
            input_data = input_data.model_dump()
        if not isinstance(input_data, dict):
            raise ValueError(f"Expected a dict or model, got {type(input_data).__name__}.")

        data = dict(input_data)
        if data.get("location") is None and data.get("lat") is not None \
                and data.get("lon") is not None:
            data["location"] = {"lat": data["lat"], "lon": data["lon"]}
        farm = data.get("farm")
        if isinstance(farm, dict):
            data.setdefault("location", farm.get("location"))
            data.setdefault("crop", farm.get("current_crop") or farm.get("crop"))
            data.setdefault("growth_stage", farm.get("growth_stage"))

        if not data.get("location") and not data.get("weather_data"):
            raise ValueError("A location (lat/lon) is required to fetch the weather forecast.")

        known = set(IrrigationRequest.model_fields)
        try:
            request = IrrigationRequest.model_validate({k: v for k, v in data.items() if k in known})
        except ValidationError as exc:
            details = "; ".join(f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}"
                                for e in exc.errors())
            raise ValueError(details) from None

        payload = request.model_dump(exclude_none=True)
        payload.update({k: data[k] for k in _PASS_THROUGH if data.get(k) is not None})
        return payload
