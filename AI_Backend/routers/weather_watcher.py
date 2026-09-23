from fastapi import APIRouter, HTTPException, Query, status

from AI_Backend.agents.crop_planning_growth.weather_watcher.agent import WeatherAgent
from AI_Backend.agents.crop_planning_growth.weather_watcher.schemas import WeatherWatcherOutput

router = APIRouter(prefix="/weather-watcher", tags=["Weather Watcher"])

weather_agent = WeatherAgent("WeatherWatcher")


@router.get(
    "/",
    response_model=WeatherWatcherOutput,
    summary="Current conditions, 14-day forecast and alerts for a farm",
    description=(
        "Check `status` first. `ok`: every provider answered. `partial`: some data "
        "is missing or served from cache after an outage - `warnings` says what. "
        "Forecast days are full local calendar days; each names its `source`."
    ),
    responses={503: {"description": "No weather provider could be reached and "
                                    "no recent forecast is cached."}},
)
async def get_weather(
    lat: float = Query(..., ge=-90, le=90, description="Latitude", examples=[23.02]),
    lon: float = Query(..., ge=-180, le=180, description="Longitude", examples=[72.57]),
):
    result = await weather_agent.run({"lat": lat, "lon": lon})
    if result.get("status") == "unavailable":
        # Not a 200 with empty lists: a client must not mistake "no data" for
        # "no rain, no alerts".
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"message": "Weather data is unavailable right now. Please retry shortly.",
                    "warnings": result.get("warnings", [])},
        )
    return result


@router.get("/health", summary="Provider configuration and cache counters")
async def health() -> dict:
    return weather_agent.health()
