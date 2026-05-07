from fastapi import APIRouter, Depends, HTTPException, status
import logging
from sqlalchemy.ext.asyncio import AsyncSession
# Import get_db from Backend module (parent directory)
from Backend.app.core.config import get_db
from AI_Backend.agents.crop_planning_growth.irrigation_planner.agent import IrrigationAgent
from AI_Backend.agents.crop_planning_growth.irrigation_planner.schemas import Location, IrrigationPlannerResponse
from AI_Backend.services.soil_repository import SoilRepository

# Irrigation by crop type and variety is still pending 

router = APIRouter(
    prefix="/irrigation-planner",
    tags=["Irrigation Planner - Provides optimized day-wise irrigation plans"]
)

logger = logging.getLogger(__name__)

@router.post("/plan-irrigation/{farm_id}", response_model=IrrigationPlannerResponse)
async def get_irrigation(
    farm_id: str, 
    location: Location, 
    db: AsyncSession = Depends(get_db)
) -> IrrigationPlannerResponse:
    """
    Generate an optimized irrigation plan for a farm
    
    Args:
        farm_id: Unique identifier for the farm
        location: Farm location with latitude and longitude
        db: Database session
        
    Returns:
        IrrigationPlannerResponse: Detailed irrigation plan with schedule, water savings, and alerts
    """
    try:
        logger.info(f"Generating irrigation plan for farm: {farm_id}")
        
        # Fetch latest soil data
        soil_repo = SoilRepository()
        soil_data = await soil_repo.get_latest_soil_data(farm_id, db)
        
        if not soil_data:
            logger.warning(f"No soil data found for farm {farm_id}")
            soil_data = {}
        
        # Create agent and run
        irrigation_agent = IrrigationAgent()
        result = await irrigation_agent.run(
            input_data={
                "soil_data": soil_data, 
                "location": location.model_dump()
            }
        )
        
        logger.info(f"Successfully generated irrigation plan for farm {farm_id}")
        return result
        
    except ValueError as e:
        logger.error(f"Validation error for farm {farm_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error generating irrigation plan for farm {farm_id}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while generating the irrigation plan"
        )