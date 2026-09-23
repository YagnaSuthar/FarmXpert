"""
Orchestrator → Task Scheduler adapters.

Pure-function translators that map the output of a specialist agent
(Soil Health, Irrigation, Weather, …) into the matching `*_agent` block
of the Task Scheduler's SchedulerInput.

The adapters live in the orchestrator because the orchestrator is the
component that owns wiring between agents. They do not modify the
upstream agent's public input/output in any way.
"""

from AI_Backend.agents.farm_operations_automation.task_scheduler.adapters.soil_health_to_scheduler import (
    soil_health_output_to_scheduler_block,
)
from AI_Backend.agents.farm_operations_automation.task_scheduler.adapters.weather_watcher_to_scheduler import (
    weather_output_to_scheduler_block,
)
from AI_Backend.agents.farm_operations_automation.task_scheduler.adapters.irrigation_to_scheduler import (
    irrigation_output_to_scheduler_block,
)
from AI_Backend.agents.farm_operations_automation.task_scheduler.adapters.market_intelligence_to_scheduler import (
    market_insights_to_scheduler_block,
)
from AI_Backend.agents.farm_operations_automation.task_scheduler.adapters.crop_prediction_to_scheduler import (
    crop_prediction_output_to_scheduler_block,
)

__all__ = [
    "soil_health_output_to_scheduler_block",
    "weather_output_to_scheduler_block",
    "irrigation_output_to_scheduler_block",
    "market_insights_to_scheduler_block",
    "crop_prediction_output_to_scheduler_block",
]
