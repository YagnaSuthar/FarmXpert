from fastapi import APIRouter, HTTPException, status
import logging
from AI_Backend.agents.crop_planning_growth.crop_selector.agent import CropSelectorAgent
from AI_Backend.agents.crop_planning_growth.crop_selector.schemas import CropSelectorRequest, CropSelectorResponse


router = APIRouter(prefix="/crop-selector", tags=["Crop Selector"])

crop_selector_agent = CropSelectorAgent()

logger = logging.getLogger(__name__)


@router.post("/recommendations", response_model=CropSelectorResponse)
async def recommend_crops(payload: CropSelectorRequest):
    try:
        result = await crop_selector_agent.recoomend_crops(payload.model_dump())
        return result
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error in crop recommendations: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while generating recommendations"
        )
    
