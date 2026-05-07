#  input and output schemas for Irrigation agent API endpoint 
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime

class Location(BaseModel):
    lat: float
    lon: float

class NPKValues(BaseModel):
    nitrogen: float = Field(default=0, description="Nitrogen content (mg/kg)")
    phosphorus: float = Field(default=0, description="Phosphorus content (mg/kg)")
    potassium: float = Field(default=0, description="Potassium content (mg/kg)")

class SoilConditions(BaseModel):
    npk: NPKValues
    soil_ph: float = Field(description="Soil pH value")
    electrical_conductivity: float = Field(description="EC in dS/m")
    current_moisture: float = Field(description="Current soil moisture in mm")

class DailyScheduleItem(BaseModel):
    date: str = Field(description="Date for the irrigation schedule")
    irrigation_required: bool = Field(description="Whether irrigation is needed")
    water_depth_mm: Optional[float] = Field(None, description="Water depth required in mm")
    duration_hours: Optional[float] = Field(None, description="Irrigation duration in hours")
    timing: Optional[str] = Field(None, description="Optimal irrigation timing")
    reason: str = Field(description="Reason for irrigation decision")
    soil_conditions: Optional[SoilConditions] = Field(None, description="Soil conditions at time of irrigation")

class Alert(BaseModel):
    type: str = Field(description="Alert type (warning, heavy_rainfall, soil_concern)")
    severity: Optional[str] = Field(None, description="Severity level (high, medium, low)")
    message: str = Field(description="Alert message")
    date: Optional[str] = Field(None, description="Date of alert")
    recommendation: Optional[str] = Field(None, description="Recommended action")

class WaterSavings(BaseModel):
    optimized_usage_liters: float = Field(description="Optimized water usage in liters")
    traditional_usage_liters: float = Field(description="Traditional method water usage in liters")
    savings_percentage: float = Field(description="Water savings percentage")

class WeatherInsights(BaseModel):
    current_weather: dict = Field(description="Current weather conditions")
    forecast_days: int = Field(description="Number of forecast days available")

class SoilHealthInsights(BaseModel):
    npk_status: NPKValues = Field(description="NPK status")
    soil_ph: float = Field(description="Soil pH")
    electrical_conductivity: float = Field(description="Electrical conductivity")
    health_score: Optional[float] = Field(None, description="Overall soil health score (0-100)")
    health_status: Optional[str] = Field(None, description="Soil health status")
    critical_factors: List[str] = Field(default=[], description="Critical factors affecting irrigation")

class IrrigationPlannerResponse(BaseModel):
    irrigation_schedule: List[DailyScheduleItem] = Field(description="Daily irrigation schedule")
    water_savings: WaterSavings = Field(description="Water savings analysis")
    weather_insights: WeatherInsights = Field(description="Weather insights")
    soil_health_insights: SoilHealthInsights = Field(description="Soil health analysis")
    alerts: List[Alert] = Field(default=[], description="Important alerts and recommendations")
    processed_at: str = Field(description="Timestamp when the plan was generated")
    summary: Optional[str] = Field(None, description="Human-readable summary of the irrigation plan")