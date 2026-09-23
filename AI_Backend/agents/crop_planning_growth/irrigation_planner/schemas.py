"""
Irrigation Planner Agent — Schemas
===================================
Designed so the orchestrator can compose human-friendly answers without
guessing what the agent meant. Every decision is machine-parseable
(decision_code + structured reasons) — the orchestrator turns it into
natural language for the farmer.
"""

from __future__ import annotations

from datetime import date as date_t
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


# ─────────────────────────────────────────────────────────────────────────────
# INPUT
# ─────────────────────────────────────────────────────────────────────────────

class Location(BaseModel):
    lat: float = Field(..., ge=-90.0, le=90.0)
    lon: float = Field(..., ge=-180.0, le=180.0)


class IrrigationRequest(BaseModel):
    """What the planner needs to know about one field."""
    model_config = ConfigDict(json_schema_extra={"example": {
        "location": {"lat": 23.02, "lon": 72.57},
        "crop": "groundnut", "days_after_sowing": 55, "soil_type": "Black Cotton",
        "soil_moisture_percent": 27.0, "electrical_conductivity": 0.8,
        "irrigation_method": "sprinkler", "farm_area_hectares": 1.5,
    }})

    location: Optional[Location] = Field(None, description="Needed to fetch the weather forecast")
    farm_id: Optional[str] = Field(None, description="Used to load the latest stored soil reading")

    crop: Optional[str] = Field(None, description="e.g. cotton, groundnut, wheat. "
                                                  "Omitted: planned for a reference crop.")
    growth_stage: Optional[str] = Field(
        None, description="germination | seedling | vegetative | flowering | fruiting | "
                          "maturation | harvest_ready | panicle_initiation (rice)")
    days_after_sowing: Optional[int] = Field(
        None, ge=0, le=730, description="Alternative to growth_stage - the stage is derived")
    sowing_date: Optional[date_t] = Field(None, description="Alternative to days_after_sowing")

    soil_type: Optional[str] = Field(
        None, description="sandy | sandy_loam | loamy | silt | clay_loam | clay | "
                          "black_cotton | alluvial | red_laterite | peaty "
                          "(crop-prediction names like 'Black Cotton' also accepted)")
    soil_moisture_percent: Optional[float] = Field(
        None, ge=0, le=100, description="Volumetric water content from the sensor, %")
    electrical_conductivity: Optional[float] = Field(
        None, ge=0, le=30, description="Soil EC, dS/m")
    water_ec_ds_m: Optional[float] = Field(
        None, ge=0, le=20, description="Irrigation water EC, dS/m - enables the "
                                       "FAO-29 leaching requirement")

    irrigation_method: Optional[str] = Field(
        None, description="drip | sprinkler | center_pivot | furrow | border | basin | flood")
    farm_area_hectares: float = Field(1.0, gt=0, le=10000)
    planning_horizon_days: int = Field(7, ge=1, le=14)

    soil_data: Optional[Dict[str, Any]] = Field(
        None, description="Raw Soil Health readings (soil_moisture, electrical_conductivity, ...)")


class NPKValues(BaseModel):
    """As measured - None when not measured, never a stand-in value."""
    nitrogen:   Optional[float] = Field(default=None, description="Nitrogen (mg/kg)")
    phosphorus: Optional[float] = Field(default=None, description="Phosphorus (mg/kg)")
    potassium:  Optional[float] = Field(default=None, description="Potassium (mg/kg)")


# ─────────────────────────────────────────────────────────────────────────────
# DAILY DECISION
# ─────────────────────────────────────────────────────────────────────────────

class IrrigationReason(BaseModel):
    """
    Structured reason a decision was made — orchestrator renders to text.

    Example: {code: "SOIL_BELOW_TARGET", factor: "soil_moisture",
              value: 42.0, threshold: 60.0, unit: "mm"}
    """
    code:      str = Field(..., description="Reason code, e.g. SOIL_BELOW_TARGET")
    factor:    str = Field(..., description="Variable that triggered it (soil_moisture, rainfall_mm, etc.)")
    value:     Optional[float] = Field(None, description="Observed value")
    threshold: Optional[float] = Field(None, description="Boundary crossed")
    unit:      Optional[str]   = Field(None, description="mm | % | dS/m | C")
    severity:  str = Field("info", description="info | low | medium | high | critical")


class DailyScheduleItem(BaseModel):
    """One day of the plan — fully machine-readable."""
    date:                  str
    decision_code:         str  = Field(..., description="See config.Decision enum")
    irrigation_required:   bool = Field(..., description="True iff water should be applied")

    water_depth_mm:        Optional[float] = Field(
        None, ge=0, description="Gross depth to apply (net need / method efficiency)")
    net_irrigation_mm:     Optional[float] = Field(
        None, ge=0, description="Water the root zone needs; the gross depth covers losses")
    sets:                  Optional[int]   = Field(
        None, ge=1, description="Working days the application is split over")
    water_volume_liters:   Optional[float] = Field(None, ge=0, description="depth × area")
    duration_hours:        Optional[float] = Field(None, ge=0)
    timing:                Optional[str]   = Field(None, description="early_morning | late_morning | evening | night")
    method:                Optional[str]   = Field(None, description="drip | sprinkler | flood | furrow | …")

    reasons:               List[IrrigationReason] = Field(default_factory=list)
    recommendation:        Optional[str] = Field(None, description="Short professional advice for orchestrator")
    alternative:           Optional[str] = Field(None, description="What to do if primary recommendation isn't viable")

    # Water balance for this day — supports farmer Q&A like
    # "why did you skip today?" or "how much did the rain cover?"
    water_balance_mm: Dict[str, float] = Field(
        default_factory=dict,
        description="{moisture_before, moisture_after (root-zone water, mm), et0_mm, etc_mm, "
                    "effective_rain_mm, irrigation_mm, depletion_mm, raw_mm}",
    )

    crop_coefficient_kc:   Optional[float] = Field(None, ge=0.1, le=1.5)
    growth_stage:          Optional[str] = None


# ─────────────────────────────────────────────────────────────────────────────
# ALERTS & RECOMMENDATIONS
# ─────────────────────────────────────────────────────────────────────────────

class Alert(BaseModel):
    type:           str = Field(..., description="warning | heavy_rainfall | soil_concern | salinity | heat | drainage")
    severity:       str = Field("medium")
    message:        str
    date:           Optional[str] = None
    recommendation: Optional[str] = None


class FarmerAction(BaseModel):
    """Atomic next-step the orchestrator can speak to the farmer."""
    action_code:    str  = Field(..., description="IRRIGATE_TODAY | INSPECT_SOIL | LEACH_SALT | DRAIN_FIELD | NO_ACTION")
    priority:       str  = Field("medium", description="low | medium | high | critical")
    summary:        str
    target_date:    Optional[str] = None
    target_field:   Optional[str] = None


# ─────────────────────────────────────────────────────────────────────────────
# CONTEXT BLOCKS
# ─────────────────────────────────────────────────────────────────────────────

class WaterSavings(BaseModel):
    optimized_usage_liters:    float
    traditional_usage_liters:  float
    savings_percentage:        float


class WeatherInsights(BaseModel):
    current_weather: Dict[str, Any] = Field(default_factory=dict)
    forecast_days:   int            = 0
    source:          str            = "weather_agent"


class SoilHealthInsights(BaseModel):
    npk_status:               NPKValues
    soil_ph:                  Optional[float] = None
    electrical_conductivity:  Optional[float] = None
    salinity_relative_yield_percent: Optional[float] = Field(
        None, description="Maas-Hoffman expected yield at this EC, % of non-saline")
    health_score:             Optional[float] = None
    health_status:            Optional[str]   = None
    critical_factors:         List[str]       = Field(default_factory=list)


class CropProfile(BaseModel):
    """Crop / soil intelligence applied for this plan — orchestrator can quote it."""
    crop:                str
    growth_stage:        Optional[str] = None
    soil_type:           str
    water_management:    str = Field(..., description="upland | paddy")
    root_depth_m:        float
    field_capacity_mm:   float = Field(..., description="Root-zone water at field capacity, mm")
    wilting_point_mm:    float = Field(..., description="Root-zone water at wilting point, mm")
    total_available_water_mm:    Optional[float] = Field(None, description="FAO-56 TAW")
    readily_available_water_mm:  Optional[float] = Field(None, description="FAO-56 RAW = p x TAW")
    depletion_fraction_p:        Optional[float] = None
    application_efficiency:      Optional[float] = None
    et0_source:                  Optional[str] = Field(
        None, description="fao56_penman_monteith | hargreaves_fallback | none")
    preferred_method:    str
    notes:               List[str] = Field(default_factory=list)


# ─────────────────────────────────────────────────────────────────────────────
# TOP-LEVEL OUTPUT — what the agent returns
# ─────────────────────────────────────────────────────────────────────────────

class NextIrrigationSummary(BaseModel):
    """Direct answer to 'when is my next irrigation?'."""
    date:           Optional[str] = None
    water_depth_mm: Optional[float] = None
    method:         Optional[str] = None
    timing:         Optional[str] = None
    reason:         Optional[str] = None


class PlanSummary(BaseModel):
    """Structured (NOT pre-formatted) summary — orchestrator humanises."""
    plan_horizon_days:        int
    irrigation_days:          int
    skip_days:                int
    total_water_mm:           float
    total_water_liters:       float
    high_severity_alerts:     int
    headline:                 str = Field(..., description="One-sentence professional headline.")


class IrrigationPlannerResponse(BaseModel):
    """Complete agent output. JSON only — the orchestrator builds the prose."""
    # Provenance
    agent_id:      str = "irrigation_agent"
    agent_version: str = "3.0.0"
    processed_at:  str
    status:        str = Field("ok", description="ok | partial (weather or soil data missing)")

    # Daily plan
    irrigation_schedule: List[DailyScheduleItem]

    # Context / why-this-plan
    crop_profile:         CropProfile
    water_savings:        WaterSavings
    weather_insights:     WeatherInsights
    soil_health_insights: SoilHealthInsights

    # Farmer-facing summaries
    summary:                 PlanSummary
    next_irrigation:         NextIrrigationSummary
    farmer_actions:          List[FarmerAction] = Field(default_factory=list)
    crop_specific_advice:    List[str]          = Field(default_factory=list)
    alerts:                  List[Alert]        = Field(default_factory=list)

    # Quality signals
    confidence:           float = Field(0.8, ge=0.0, le=1.0)
    data_quality_score:   float = Field(0.8, ge=0.0, le=1.0)
    warnings:             List[str] = Field(default_factory=list)

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "agent_id": "irrigation_agent",
            "agent_version": "3.0.0",
            "irrigation_schedule": [{
                "date": "2026-06-21",
                "decision_code": "IRRIGATE",
                "irrigation_required": True,
                "water_depth_mm": 18.0,
                "duration_hours": 1.8,
                "timing": "early_morning",
                "method": "drip",
                "reasons": [
                    {"code": "SOIL_BELOW_TARGET", "factor": "soil_moisture",
                     "value": 42.0, "threshold": 60.0, "unit": "mm",
                     "severity": "medium"},
                    {"code": "CROP_CRITICAL_STAGE", "factor": "growth_stage",
                     "value": None, "threshold": None, "unit": None,
                     "severity": "high"},
                ],
                "recommendation": "Apply 18 mm at 06:00 via drip to refill root zone before flowering peak.",
                "alternative": "If drip unavailable, 8 mm sprinkler before 09:00.",
            }],
        }
    })
