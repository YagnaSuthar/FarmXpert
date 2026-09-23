import logging

from fastapi import APIRouter, HTTPException, status

from AI_Backend.agents.crop_planning_growth.soil_health.agent import SoilHealthAgent
from AI_Backend.agents.crop_planning_growth.soil_health.config import CROP_CONFIG, SOIL_TYPE_CONFIG
from AI_Backend.agents.crop_planning_growth.soil_health.schemas import SoilHealthInput, SoilHealthOutput

router = APIRouter()
logger = logging.getLogger(__name__)
soil_agent = SoilHealthAgent()


@router.post(
    "/analyze",
    response_model=SoilHealthOutput,
    summary="Analyze soil health",
    description=(
        "Only soil_ph and electrical_conductivity are required. Moisture is read as "
        "plant-available water for the given soil_type; crop_type sets the optimal ranges, "
        "salt tolerance and legume nitrogen advice."
    ),
)
async def analyze_soil_health(data: SoilHealthInput):
    try:
        return await soil_agent.run(data)
    except Exception as exc:  # noqa: BLE001
        logger.error("Soil analysis failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail="Soil analysis failed.")


@router.get("/options", summary="Crops and soil types the analysis knows")
async def options() -> dict:
    return {"crops": sorted(CROP_CONFIG), "soil_types": sorted(SOIL_TYPE_CONFIG)}
