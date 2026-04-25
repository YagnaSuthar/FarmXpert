# routers/soil_health.py

from fastapi import APIRouter, HTTPException
from agents.crop_planning_growth.soil_Health.schemas import SoilHealthInput, SoilHealthOutput
from agents.crop_planning_growth.soil_Health.agent import SoilHealthAgent

router = APIRouter()

# Initialize agent once
soil_agent = SoilHealthAgent()


@router.post(
    "/analyze",
    response_model=SoilHealthOutput,
    summary="Analyze Soil Health",
    description="Takes soil sensor data and returns health score, alerts, fertilizer recommendations, and suggestions."
)
async def analyze_soil_health(data: SoilHealthInput):
    """
    Main endpoint for soil health analysis.

    Accepts 9 required soil/air parameters + optional context fields.
    Returns score (0-100), status, alerts, fertilizers, and suggestions.
    """
    try:
        result = soil_agent.run(data)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Soil analysis failed: {str(e)}")
