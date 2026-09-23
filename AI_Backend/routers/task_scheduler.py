import logging

from fastapi import APIRouter, HTTPException, status
from pydantic import ValidationError

from AI_Backend.agents.farm_operations_automation.task_scheduler.agent import TaskSchedulerAgent
from AI_Backend.agents.farm_operations_automation.task_scheduler.config import (
    AGENT_VERSION,
    CATEGORY_CONFIG,
    DEFAULT_HORIZON_DAYS,
    MAX_HORIZON_DAYS,
)
from AI_Backend.agents.farm_operations_automation.task_scheduler.playbook import known_crops
from AI_Backend.agents.farm_operations_automation.task_scheduler.schemas import (
    SchedulerInput,
    TaskPlan,
)

router = APIRouter(prefix="/api/task-scheduler", tags=["Task Scheduler"])
logger = logging.getLogger(__name__)
scheduler_agent = TaskSchedulerAgent()


@router.post(
    "/plan",
    response_model=TaskPlan,
    summary="Build the farm's work plan",
    description=(
        "Turns the specialist agents' outputs into a day-by-day plan: what to do, when, "
        "why it matters now, what not to do, and what waiting costs. Pass any subset of the "
        "agent blocks - a plan built from the weather alone is still useful. Planning is "
        "pure computation: no database, no outbound calls."
    ),
)
async def build_plan(request: SchedulerInput) -> TaskPlan:
    try:
        return scheduler_agent.plan(request)
    except ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail=f"Input could not be read: {exc.error_count()} problem(s).")
    except Exception as exc:  # noqa: BLE001
        logger.error("Task planning failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail="Task planning failed.")


@router.get("/options", summary="What the scheduler knows")
async def options() -> dict:
    return {
        "version": AGENT_VERSION,
        "task_categories": {
            name: {"display_name": cfg["display_name"],
                   "typical_duration_minutes": cfg["duration_min"],
                   "people_needed": cfg["labor"]}
            for name, cfg in CATEGORY_CONFIG.items()
        },
        "crops_with_specific_advice": known_crops(),
        "planning_horizon_days": {"default": DEFAULT_HORIZON_DAYS, "max": MAX_HORIZON_DAYS},
    }


@router.get("/health", summary="Liveness probe")
async def health() -> dict:
    return {"status": "ok", "agent": scheduler_agent.AGENT_ID, "version": AGENT_VERSION}
