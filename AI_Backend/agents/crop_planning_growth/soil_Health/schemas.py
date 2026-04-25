# app/soil_health/schemas.py

from pydantic import BaseModel, Field
from typing import List, Optional


# ── INPUT ────────────────────────────────────────────────
class SoilHealthInput(BaseModel):
    soil_moisture: float = Field(..., example=45.0)
    soil_temperature: float = Field(..., example=25.0)
    soil_ph: float = Field(..., example=6.5)
    nitrogen: float = Field(..., example=80.0)
    phosphorus: float = Field(..., example=40.0)
    potassium: float = Field(..., example=50.0)
    electrical_conductivity: float = Field(..., example=0.5)
    air_temperature: float = Field(..., example=30.0)
    air_humidity: float = Field(..., example=70.0)

    soil_type: Optional[str] = Field(None, example="Loamy")
    crop_type: Optional[str] = Field(None, example="Wheat")
    rainfall: Optional[float] = Field(None, example=120.0)
    irrigation_type: Optional[str] = Field(None, example="Drip")
    irrigation_amount: Optional[float] = Field(None, example=5.0)
    fertilizer_type: Optional[str] = Field(None, example="Urea")
    fertilizer_amount: Optional[float] = Field(None, example=40.0)


# ── SUB-MODELS ───────────────────────────────────────────
class Alert(BaseModel):
    type: str
    message: str
    severity: str   # low | medium | high


class FertilizerRecommendation(BaseModel):
    name: str
    advice: str


class Suggestion(BaseModel):
    message: str


class ConfidenceScore(BaseModel):
    type: str       # "rule-based"
    score: float    # 0.0 – 1.0


# ── OUTPUT ───────────────────────────────────────────────
class SoilHealthOutput(BaseModel):
    soil_health_score: float
    soil_health_status: str
    summary: str
    confidence: ConfidenceScore
    data_quality_score: float
    critical_factors: List[str]

    alerts: List[Alert]
    fertilizers: List[FertilizerRecommendation]
    suggestions: List[Suggestion]