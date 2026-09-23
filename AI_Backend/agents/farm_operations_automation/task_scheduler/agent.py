"""
TaskSchedulerAgent — turns the other agents' findings into the farmer's day.

  TaskSchedulerAgent().run(payload)  -> dict matching TaskPlan
  TaskSchedulerAgent()(state)        -> LangGraph node; never raises

`run()` accepts a SchedulerInput, a dict in that shape, or orchestrator
state carrying the specialist agents' raw outputs (see inputs.normalise).
Planning is pure CPU work with no I/O, so it is fast enough to run inline;
the async signature exists only to match the other agents.
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import ValidationError

from AI_Backend.agents.farm_operations_automation.task_scheduler.config import (
    AGENT_ID,
    AGENT_VERSION,
)
from AI_Backend.agents.farm_operations_automation.task_scheduler.inputs import normalise
from AI_Backend.agents.farm_operations_automation.task_scheduler.schemas import (
    SchedulerInput,
    TaskPlan,
)
from AI_Backend.agents.farm_operations_automation.task_scheduler.service import (
    TaskSchedulerService,
)

logger = logging.getLogger("farmxpert.task_scheduler")


class TaskSchedulerAgent:
    AGENT_ID = AGENT_ID
    AGENT_VERSION = AGENT_VERSION

    def __init__(self) -> None:
        self.service = TaskSchedulerService()

    async def __call__(self, state: Any) -> dict:
        """LangGraph node. A farm day is worth planning even when one
        upstream agent failed, but unusable input must not stop the graph."""
        try:
            return {"task_plan": await self.run(state)}
        except (ValidationError, TypeError, ValueError) as exc:
            logger.warning("Task scheduling skipped - input unusable: %s", exc)
            return {}

    async def run(self, payload: Any) -> dict:
        """Build the plan. Returns a JSON-safe dict matching TaskPlan."""
        return self.plan(payload).model_dump(mode="json")

    def plan(self, payload: Any) -> TaskPlan:
        """Same as run(), but returns the typed TaskPlan."""
        request = payload if isinstance(payload, SchedulerInput) \
            else SchedulerInput.model_validate(normalise(payload))
        return self.service.run(request)
