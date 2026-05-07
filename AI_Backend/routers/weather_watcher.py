from fastapi import APIRouter
from AI_Backend.agents.crop_planning_growth.weather_watcher.agent import WeatherAgent


router = APIRouter(prefix="/weather-watcher",tags=["This API gives Weather Related Data to the agents/user"])

weather_agent = WeatherAgent("WeatherWatcher")

@router.get("/")
async def get_weather(lat: float, lon: float):
    result = await weather_agent.run({
        "lat": lat,
        "lon": lon
    })
    return result  