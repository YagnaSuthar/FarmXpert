# state.py
from typing import TypedDict, Optional

class FarmState(TypedDict):
    query: str
    lat: float
    lon: float
    weather_data: Optional[dict]
    soil_data: Optional[dict]
    irrigation_advice: Optional[str]
    crop_recommendation: Optional[dict]