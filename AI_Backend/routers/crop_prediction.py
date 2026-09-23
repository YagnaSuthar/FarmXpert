import logging

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import ValidationError

from AI_Backend.agents.crop_planning_growth.crop_prediction.agent import CropPredictionAgent
from AI_Backend.agents.crop_planning_growth.crop_prediction.model_loader import (
    UnknownRegionError,
)
from AI_Backend.agents.crop_planning_growth.crop_prediction.schemas import (
    CropPredictionRequest,
    CropPredictionResponse,
)

router = APIRouter(prefix="/crop-prediction", tags=["Crop Prediction"])

crop_prediction_agent = CropPredictionAgent()

logger = logging.getLogger(__name__)


@router.post(
    "/predict",
    response_model=CropPredictionResponse,
    summary="Rank the crops worth considering on a field",
    description=(
        "Returns up to five crops ranked by suitability, each with varieties and the "
        "named agronomic checks behind the score.\n\n"
        "**Branch on `status`.** `no_suitable_crop` means no crop in the database suits "
        "this field; show `message` and do not present `closest` as a recommendation. "
        "Show the top three rather than the top one: top-1 accuracy is 80.6%, top-3 is 99.0%."
    ),
    responses={
        422: {"description": "Bad reading, wrong unit, or unknown region."},
        503: {"description": "Model artifacts unavailable."},
        504: {"description": "Scoring exceeded its time budget."},
    },
)
async def predict_crops(
    payload: CropPredictionRequest, response: Response
) -> CropPredictionResponse:
    try:
        result = await crop_prediction_agent.predict(payload)
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=CropPredictionAgent.format_validation_error(exc),
        )
    except UnknownRegionError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    except TimeoutError as exc:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail=str(exc))
    except FileNotFoundError as exc:
        logger.error("Crop prediction model artifacts missing: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Crop prediction model is not available.",
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("Error in crop prediction: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while generating crop predictions",
        )

    # Correlation id and cache state as headers too, so they survive in the
    # access log and in clients that never read the body.
    if result.request_id:
        response.headers["X-Request-ID"] = result.request_id
    response.headers["X-Cache"] = "HIT" if result.cached else "MISS"
    return result


@router.get(
    "/health",
    summary="Readiness, validated metrics and live cache counters",
    responses={503: {"description": "Model not loaded yet."}},
)
async def health(response: Response) -> dict:
    report = crop_prediction_agent.health()
    if not report.get("model_loaded"):
        # Readiness, not liveness: the process is up but must not take traffic.
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return report


@router.get("/regions", summary="Regions the variety table covers")
async def regions() -> dict:
    report = crop_prediction_agent.health()
    return {"default": report["region"], "known_regions": report["known_regions"]}
