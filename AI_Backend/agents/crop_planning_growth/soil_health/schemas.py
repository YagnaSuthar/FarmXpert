# AI_Backend/agents/crop_planning_growth/soil_health/schemas.py
"""
Pydantic schemas for the Soil Health Agent.
Config version: 2.0 — richer fertilizer objects, weather alerts,
conflict detection output, and separated alert sources.
"""

from __future__ import annotations
from pydantic import BaseModel, ConfigDict, Field
from typing import List, Literal, Optional


# =============================================================================
# INPUT SCHEMA
# =============================================================================

class SoilHealthInput(BaseModel):
    """
    Sensor readings and context for one analysis.

    Only pH and EC are required - a farmer with just a pH/EC probe still gets
    an analysis. Every other reading improves it and is reflected in
    `data_quality_score`.
    """

    # ── Required ─────────────────────────────────────────────────────────────
    soil_ph:                 float = Field(..., ge=3.0, le=10.0, examples=[7.8], description="Soil pH")
    electrical_conductivity: float = Field(..., ge=0.0, le=16.0, examples=[0.6],
                                           description="EC (dS/m), read as saturated-paste ECe")

    # ── Soil sensors ─────────────────────────────────────────────────────────
    soil_moisture:    Optional[float] = Field(None, ge=0.0, le=100.0, examples=[28.0],
                                              description="Volumetric water content (%)")
    soil_temperature: Optional[float] = Field(None, ge=-10.0, le=60.0, examples=[27.0],
                                              description="Soil temperature at 10-15 cm (°C)")
    nitrogen:         Optional[float] = Field(None, ge=0.0, le=1000.0, examples=[45.0],
                                              description="Mineral N, NO3-N + NH4-N (mg/kg)")
    phosphorus:       Optional[float] = Field(None, ge=0.0, le=500.0, examples=[16.0],
                                              description="Olsen P (mg/kg)")
    potassium:        Optional[float] = Field(None, ge=0.0, le=2000.0, examples=[140.0],
                                              description="NH4OAc-extractable K (mg/kg)")
    nutrient_source:  Literal["sensor", "lab"] = Field(
        "sensor",
        description="Where N/P/K came from. 'sensor': an in-field 7-in-1 probe, which "
                    "estimates NPK from conductivity - advisory only, no fertilizer doses. "
                    "'lab': a soil test (e.g. Soil Health Card) - full recommendations.")

    # ── Air sensors ──────────────────────────────────────────────────────────
    air_temperature:  Optional[float] = Field(None, ge=-20.0, le=55.0, description="°C")
    air_humidity:     Optional[float] = Field(None, ge=0.0, le=100.0, description="%")

    # ── Context ──────────────────────────────────────────────────────────────
    soil_type:  Optional[str] = Field(None, examples=["Black Cotton"],
                                      description="sandy | sandy_loam | loamy | silt | clay_loam | clay | "
                                                  "black_cotton | alluvial | red_laterite | peaty "
                                                  "(Loam, Black Cotton, Red Laterite ... also accepted)")
    crop_type:  Optional[str] = Field(None, examples=["groundnut"],
                                      description="wheat | rice | maize | cotton | sugarcane | soybean | "
                                                  "potato | tomato | groundnut | guar | white peas | "
                                                  "coriander | ajwain | mango")
    season:            Optional[str]   = Field(None, description="Context only")
    growth_stage:      Optional[str]   = Field(None, description="Context only")
    rainfall:          Optional[float] = Field(None, ge=0.0, le=500.0, description="Rain in the last 7 days (mm)")
    irrigation_type:   Optional[str]   = None
    irrigation_amount: Optional[float] = Field(None, ge=0.0, le=200.0, description="Irrigation in the last 7 days (mm)")
    fertilizer_type:   Optional[str]   = Field(None, examples=["urea"], description="Last fertilizer applied")
    fertilizer_amount: Optional[float] = Field(None, ge=0.0, description="kg/ha")
    field_id:          Optional[str]   = None
    region:            Optional[str]   = None

    model_config = ConfigDict(json_schema_extra={"example": {
        "soil_ph": 8.1, "electrical_conductivity": 0.6, "soil_moisture": 28.0,
        "soil_temperature": 27.0, "nitrogen": 45.0, "phosphorus": 16.0, "potassium": 140.0,
        "air_temperature": 33.0, "air_humidity": 60.0,
        "soil_type": "Black Cotton", "crop_type": "groundnut", "rainfall": 4.0,
        "fertilizer_type": "urea",
    }})


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
    soft_alert:     Optional[bool]  = Field(None, description="Mild deviation from the crop optimum")
    unit:           Optional[str]   = Field(None, description="Unit of observed_value, when not the sensor unit")
    expected_relative_yield: Optional[float] = Field(
        None, description="Salinity: Maas-Hoffman yield, % of a non-saline field")
    estimated:      Optional[bool]  = Field(None, description="From a sensor estimate, not a lab test")


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


class MoistureStatus(BaseModel):
    """The moisture reading interpreted for this soil (FAO-56 water properties)."""
    volumetric_percent:          float
    available_water_percent:     float = Field(..., description="0 = wilting point, 100 = field capacity")
    field_capacity_percent:      float
    wilting_point_percent:       float
    stress_starts_below_percent: float = Field(..., description="(1 - p) x 100 for the crop")
    soil_type_used:              str
    soil_type_assumed:           bool


class ConfidenceScore(BaseModel):
    """Model confidence in the analysis output."""
    type:  str   = Field("rule-based", description="Analysis engine type")
    score: float = Field(..., ge=0.0, le=1.0, description="0.0 (low) → 1.0 (high)")


class ValidationError(BaseModel):
    """A single input validation failure."""
    field:       str        = Field(..., description="Schema field name")
    config_key:  Optional[str] = Field(None)
    value:       Optional[float] = Field(None)
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
    agent_id:           str   = "soil_health_agent"
    agent_version:      str   = "3.0.0"
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
    moisture_status:  Optional[MoistureStatus] = None

    # ── Recommendations ──────────────────────────────────────────────────────
    fertilizers:  List[FertilizerRecommendation] = Field(default_factory=list)
    suggestions:  List[Suggestion]               = Field(default_factory=list)
    conflicts:    List[ConflictAlert]            = Field(default_factory=list)

    model_config = ConfigDict(json_schema_extra={
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
        })
