"""
SoilHealthAgent — runs the soil analysis pipeline. Domain logic lives in
SoilHealthService; this class owns only the order of the steps.

  SoilHealthAgent().run(soil_data)   -> dict matching SoilHealthOutput
  SoilHealthAgent()(state)           -> LangGraph node; never raises

`run()` accepts a SoilHealthInput, a dict of readings, or orchestrator state
with the readings nested under `soil_data`.
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import ValidationError

from AI_Backend.agents.crop_planning_growth.soil_health.config import AGENT_ID, AGENT_VERSION
from AI_Backend.agents.crop_planning_growth.soil_health.schemas import SoilHealthInput
from AI_Backend.agents.crop_planning_growth.soil_health.service import SoilHealthService

logger = logging.getLogger("farmxpert.soil_health")


class SoilHealthAgent:
    AGENT_ID = AGENT_ID
    AGENT_VERSION = AGENT_VERSION

    def __init__(self) -> None:
        self.service = SoilHealthService()

    async def __call__(self, state: Any) -> dict:
        """LangGraph node. Orchestrator state often lacks a full reading set;
        that must not stop the graph, so invalid input returns no update."""
        try:
            return await self.run(state)
        except (ValidationError, TypeError, ValueError) as exc:
            logger.warning("Soil health skipped - input unusable: %s", exc)
            return {}

    async def run(self, soil_data: Any) -> dict:
        data = self._normalise_input(soil_data)
        svc = self.service

        _, validation_errors = svc.validate(data)
        soil_alerts = svc.analyze_soil(data)
        weather_alerts = svc.analyze_weather(data)
        conflicts = svc.detect_conflicts(data, soil_alerts)

        all_alerts = list(soil_alerts) + list(weather_alerts)
        for conflict in conflicts:
            all_alerts.append({"type": "CONFLICT", "message": conflict["reason"],
                               "severity": "high", "source": "conflict", "score_impact": 5})

        score = svc.calculate_score(data, all_alerts)
        status = svc.get_status(score, alert_count=len(all_alerts))
        fertilizers = svc.recommend_fertilizers(soil_alerts, data)
        suggestions = svc.suggestions(data, all_alerts, conflicts)
        summary = svc.generate_summary(status, score, all_alerts,
                                       crop_type=getattr(data, "crop_type", None))
        critical_factors = svc.extract_critical_factors(all_alerts)

        logger.info("SoilHealthAgent v%s | crop=%s soil=%s score=%s status=%s alerts=%d",
                    self.AGENT_VERSION, data.crop_type, data.soil_type, score, status,
                    len(all_alerts))
        return {
            "agent_id": self.AGENT_ID,
            "agent_version": self.AGENT_VERSION,
            "soil_health_score": score,
            "soil_health_status": status,
            "summary": summary,
            "confidence": svc.compute_confidence(validation_errors, all_alerts),
            "data_quality_score": svc.compute_data_quality(data, validation_errors),
            "validation_errors": validation_errors,
            "alerts": all_alerts,
            "soil_alerts": soil_alerts,
            "weather_alerts": weather_alerts,
            "critical_factors": critical_factors,
            "moisture_status": svc.moisture_status(data),
            "fertilizers": fertilizers,
            "suggestions": suggestions,
            "conflicts": conflicts,
        }

    @staticmethod
    def _normalise_input(soil_data: Any) -> SoilHealthInput:
        if isinstance(soil_data, SoilHealthInput):
            return soil_data
        if isinstance(soil_data, dict):
            inner = soil_data.get("soil_data")
            if isinstance(inner, SoilHealthInput):
                return inner
            if isinstance(inner, dict) and "soil_ph" not in soil_data:
                # Orchestrator state: readings nested, context may sit at the top.
                merged = {**{k: soil_data[k] for k in ("crop_type", "soil_type") if soil_data.get(k)},
                          **inner}
                return SoilHealthInput.model_validate(merged)
            return SoilHealthInput.model_validate(soil_data)
        raise TypeError("SoilHealthAgent.run expects SoilHealthInput, a dict of readings, or "
                        f"state with 'soil_data'; got {type(soil_data).__name__}.")
