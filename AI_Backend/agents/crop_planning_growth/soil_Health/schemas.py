# app/crop_planning_growth/soil_Health/schemas.py
"""
Pydantic schemas for the Soil Health Agent.
Config version: 2.0 — richer fertilizer objects, weather alerts,
conflict detection output, and separated alert sources.
"""

from __future__ import annotations
from pydantic import BaseModel, Field
from typing import List, Optional


# =============================================================================
# INPUT SCHEMA
# =============================================================================

class SoilHealthInput(BaseModel):
    """
    All sensor readings and agronomic context for one analysis request.
    Required fields must be present; optional fields improve analysis quality
    and data_quality_score.
    """

    # ── Required: Soil Sensors ───────────────────────────────────────────────
    soil_moisture:           float = Field(..., ge=0.0,   le=100.0, example=45.0,  description="Volumetric water content (%)")
    soil_temperature:        float = Field(..., ge=-10.0, le=60.0,  example=25.0,  description="Soil temperature (°C)")
    soil_ph:                 float = Field(..., ge=3.0,   le=10.0,  example=6.5,   description="Soil pH (dimensionless)")
    nitrogen:                float = Field(..., ge=0.0,   le=1000.0,example=80.0,  description="Nitrogen (mg/kg)")
    phosphorus:              float = Field(..., ge=0.0,   le=500.0, example=40.0,  description="Phosphorus (mg/kg)")
    potassium:               float = Field(..., ge=0.0,   le=2000.0,example=50.0,  description="Potassium (mg/kg)")
    electrical_conductivity: float = Field(..., ge=0.0,   le=16.0,  example=0.5,   description="EC (dS/m)")

    # ── Required: Air Sensors ────────────────────────────────────────────────
    air_temperature:         float = Field(..., ge=-20.0, le=55.0,  example=30.0,  description="Ambient air temperature (°C)")
    air_humidity:            float = Field(..., ge=0.0,   le=100.0, example=70.0,  description="Relative humidity (%)")

    # ── Optional: Context (improve analysis accuracy) ────────────────────────
    soil_type:               Optional[str]   = Field(None, example="loamy",   description="sandy|clay|loamy|peaty|silt")
    crop_type:               Optional[str]   = Field(None, example="wheat",   description="wheat|rice|maize|cotton|sugarcane|…")
    season:                  Optional[str]   = Field(None, example="summer",  description="summer|winter|monsoon")
    growth_stage:            Optional[str]   = Field(None, example="vegetative", description="seedling|vegetative|flowering|maturity|harvest")
    rainfall:                Optional[float] = Field(None, ge=0.0, le=500.0,  example=12.0,  description="Rainfall last 7 days (mm)")
    irrigation_type:         Optional[str]   = Field(None, example="drip",    description="Type of irrigation system")
    irrigation_amount:       Optional[float] = Field(None, ge=0.0, le=200.0,  example=5.0,   description="Irrigation applied last 7 days (mm)")
    fertilizer_type:         Optional[str]   = Field(None, example="urea",    description="Last fertilizer applied (free text)")
    fertilizer_amount:       Optional[float] = Field(None, ge=0.0,            example=40.0,  description="Fertilizer amount applied (kg/ha)")
    field_id:                Optional[str]   = Field(None, example="FIELD-007",description="Unique field identifier")
    region:                  Optional[str]   = Field(None, example="Punjab",   description="Field region or state")

    class Config:
        json_schema_extra = {
            "example": {
                "soil_moisture": 38.0, "soil_temperature": 28.0, "soil_ph": 5.8,
                "nitrogen": 60.0, "phosphorus": 18.0, "potassium": 45.0,
                "electrical_conductivity": 2.1,
                "air_temperature": 36.0, "air_humidity": 78.0,
                "soil_type": "sandy", "crop_type": "wheat", "season": "summer",
                "rainfall": 2.0, "fertilizer_type": "urea",
            }
        }


# =============================================================================
# OUTPUT SUB-MODELS
# =============================================================================

class Alert(BaseModel):
    """Single soil or weather alert with provenance metadata."""
    type:           str   = Field(..., description="Alert code, e.g. LOW_N")
    message:        str   = Field(..., description="Human-readable description")
    severity:       str   = Field(..., description="info | low | medium | high | critical")
    score_impact:   float = Field(0.0,  description="Points deducted from health score")
    parameter:      Optional[str]   = Field(None, description="Sensor/param that triggered this")
    observed_value: Optional[float] = Field(None, description="Raw observed value")
    boundary:       Optional[float] = Field(None, description="Optimal boundary value crossed")
    direction:      Optional[str]   = Field(None, description="above | below")
    source:         Optional[str]   = Field(None, description="soil | weather | conflict")
    extreme_override: Optional[bool] = Field(None, description="True if extreme-value rule applied")


class FertilizerRecommendation(BaseModel):
    """Rich fertilizer recommendation mapped from an alert code."""
    triggered_by:  str         = Field(..., description="Alert code that triggered this")
    fertilizer:    str         = Field(..., description="Config fertilizer key")
    display_name:  str         = Field(..., description="Full product name with grade")
    dosage:        str         = Field(..., description="Recommended application rate")
    timing:        str         = Field(..., description="When and how often to apply")
    method:        str         = Field(..., description="Application method")
    cautions:      List[str]   = Field(default_factory=list, description="Agronomic warnings")


class Suggestion(BaseModel):
    """Actionable management suggestion."""
    message:   str = Field(..., description="Actionable suggestion text")
    priority:  str = Field("medium", description="info | low | medium | high | critical")
    source:    str = Field("alert",  description="alert | compound | conflict | default")


class ConflictAlert(BaseModel):
    """
    Fertilizer conflict: either the applied fertilizer is not working
    (INEFFECTIVE) or it is counter-productive given active conditions
    (CONTRAINDICATED).
    """
    conflict_type:        str        = Field(..., description="ineffective | contraindicated")
    fertilizer_applied:   str        = Field(..., description="Free-text name as entered")
    fertilizer_key:       str        = Field(..., description="Normalised config key")
    expected_to_fix:      Optional[List[str]] = Field(None, description="Alert codes it should resolve")
    still_present:        Optional[List[str]] = Field(None, description="Codes still active (ineffective)")
    active_conditions:    Optional[List[str]] = Field(None, description="Codes making it contraindicated")
    expected_window_days: Optional[str]       = Field(None, description="Days before expected improvement")
    reason:               str        = Field(..., description="Explanation of the conflict")
    alternative:          str        = Field("—",  description="Recommended alternative fertilizer")


class ConfidenceScore(BaseModel):
    """Model confidence in the analysis output."""
    type:  str   = Field("rule-based", description="Analysis engine type")
    score: float = Field(..., ge=0.0, le=1.0, description="0.0 (low) → 1.0 (high)")


class ValidationError(BaseModel):
    """A single input validation failure."""
    field:       str        = Field(..., description="Schema field name")
    config_key:  Optional[str] = Field(None)
    value:       float      = Field(...)
    valid_range: Optional[List[float]] = Field(None)
    allowed:     Optional[List[str]]   = Field(None)
    message:     str        = Field(...)


# =============================================================================
# OUTPUT SCHEMA
# =============================================================================

class SoilHealthOutput(BaseModel):
    """
    Full analysis output from the Soil Health Agent.
    Designed for downstream consumption by irrigation, fertilizer,
    disease, and reporting agents.
    """

    # ── Score ────────────────────────────────────────────────────────────────
    soil_health_score:  float  = Field(..., ge=0.0, le=100.0, description="Composite health score (0–100)")
    soil_health_status: str    = Field(..., description="Excellent | Good | Fair | Poor | Critical")
    summary:            str    = Field(..., description="Natural-language one-sentence summary")

    # ── Quality Signals ──────────────────────────────────────────────────────
    confidence:          ConfidenceScore = Field(..., description="Rule-engine confidence")
    data_quality_score:  float           = Field(..., ge=0.0, le=1.0, description="Input completeness (0–1)")
    validation_errors:   List[ValidationError] = Field(default_factory=list)

    # ── Alerts (unified + separated for routing) ─────────────────────────────
    alerts:           List[Alert] = Field(..., description="All alerts (soil + weather + conflict summary)")
    soil_alerts:      List[Alert] = Field(default_factory=list, description="Soil parameter alerts only")
    weather_alerts:   List[Alert] = Field(default_factory=list, description="Weather-triggered alerts only")
    critical_factors: List[str]   = Field(default_factory=list, description="HIGH/CRITICAL alert type codes")

    # ── Recommendations ──────────────────────────────────────────────────────
    fertilizers:  List[FertilizerRecommendation] = Field(default_factory=list)
    suggestions:  List[Suggestion]               = Field(default_factory=list)
    conflicts:    List[ConflictAlert]            = Field(default_factory=list)

    class Config:
        json_schema_extra = {
            "example": {
                "soil_health_score": 54.3,
                "soil_health_status": "Fair",
                "summary": "Soil health is fair due to nitrogen deficiency, elevated salinity, and drought risk.",
                "confidence": {"type": "rule-based", "score": 0.88},
                "data_quality_score": 0.84,
                "validation_errors": [],
                "critical_factors": ["CRITICAL_LOW_N", "HIGH_EC"],
                "alerts": [
                    {"type": "CRITICAL_LOW_N", "message": "Severe nitrogen deficiency…", "severity": "critical", "score_impact": 20},
                    {"type": "HIGH_EC", "message": "High salinity detected…", "severity": "medium", "score_impact": 10},
                ],
                "fertilizers": [
                    {
                        "triggered_by": "CRITICAL_LOW_N",
                        "fertilizer": "ammonium_sulfate",
                        "display_name": "Ammonium Sulphate (21-0-0-24S)",
                        "dosage": "80–120 kg/ha",
                        "timing": "Apply immediately; consider foliar urea 2% as emergency.",
                        "method": "soil_application_with_irrigation",
                        "cautions": ["Monitor pH — ammonium sulfate acidifies soil slightly."],
                    }
                ],
                "suggestions": [{"message": "Apply nitrogen immediately…", "priority": "critical", "source": "alert"}],
                "conflicts": [],
            }
        }