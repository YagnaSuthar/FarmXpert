import logging

from fastapi import APIRouter, HTTPException, status

from AI_Backend.agents.crop_planning_growth.irrigation_planner.agent import IrrigationAgent
from AI_Backend.agents.crop_planning_growth.irrigation_planner.config import (
    CROP_CONFIG,
    METHODS,
    SOIL_CONFIG,
)
from AI_Backend.agents.crop_planning_growth.irrigation_planner.schemas import (
    IrrigationPlannerResponse,
    IrrigationRequest,
)

router = APIRouter(prefix="/irrigation-planner", tags=["Irrigation Planner"])

logger = logging.getLogger(__name__)
irrigation_agent = IrrigationAgent()


async def _plan(payload: dict) -> dict:
    try:
        return await irrigation_agent.run(payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    except Exception as exc:  # noqa: BLE001
        logger.error("Irrigation planning failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail="An error occurred while generating the irrigation plan.")


@router.post(
    "/plan",
    response_model=IrrigationPlannerResponse,
    summary="Day-by-day irrigation plan for one field (FAO-56 water balance)",
    description=(
        "Name the crop and its stage (or days after sowing), the soil type and, ideally, "
        "the current soil moisture. With `farm_id` and no moisture reading, the latest "
        "stored reading is used. `water_depth_mm` is what to apply; `net_irrigation_mm` "
        "is what the roots need after application losses."
    ),
)
async def plan_irrigation(request: IrrigationRequest) -> dict:
    payload = request.model_dump(exclude_none=True)
    if request.farm_id and request.soil_moisture_percent is None and not request.soil_data:
        stored, problem = await _stored_soil_reading(request.farm_id)
        if stored:
            payload["soil_data"] = stored
    return await _plan(payload)


@router.get("/options", summary="Crops, soils and methods the planner knows")
async def options() -> dict:
    return {"crops": sorted(CROP_CONFIG), "soil_types": sorted(SOIL_CONFIG),
            "methods": {m: {"application_efficiency": v["efficiency"]} for m, v in METHODS.items()}}
