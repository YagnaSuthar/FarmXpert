"""Request/response contract for the crop prediction agent.

The boundary does the unit checking, because a wrong unit does not fail - it
returns plausible nonsense.  An EC of 580 passed as dS/m instead of 0.58
vetoes every variety on the field and the farmer is told nothing grows here.
So EC must be supplied in a named unit, and readings outside physical range
are rejected rather than scored.
"""
from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class SoilType(str, Enum):
    """Exactly the ten soil classes the model was built against."""
    SANDY = "Sandy"
    SANDY_LOAM = "Sandy Loam"
    RED_LATERITE = "Red Laterite"
    LOAM = "Loam"
    SILTY_LOAM = "Silty Loam"
    ALLUVIAL = "Alluvial"
    CLAY_LOAM = "Clay Loam"
    BLACK_COTTON = "Black Cotton"
    CLAY = "Clay"
    SALINE_ALKALINE = "Saline-Alkaline"


class Month(str, Enum):
    JANUARY = "January"
    FEBRUARY = "February"
    MARCH = "March"
    APRIL = "April"
    MAY = "May"
    JUNE = "June"
    JULY = "July"
    AUGUST = "August"
    SEPTEMBER = "September"
    OCTOBER = "October"
    NOVEMBER = "November"
    DECEMBER = "December"


class PredictionStatus(str, Enum):
    OK = "ok"
    NO_SUITABLE_CROP = "no_suitable_crop"


# Outside this the reading is a sensor fault, not a field: reject it.
PH_PHYSICAL = (3.0, 10.0)
# Outside this the model has no support; still scored, but flagged.
PH_SUPPORTED = (5.1, 9.0)
EC_PHYSICAL_DS_M = (0.0, 30.0)


class Location(BaseModel):
    lat: float = Field(..., ge=-90.0, le=90.0, examples=[23.02])
    lon: float = Field(..., ge=-180.0, le=180.0, examples=[72.57])


class CropPredictionRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [{
                "farm_id": "farm-sunrise-001",
                "ph": 8.0,
                "ec_us_cm": 580,
                "moisture_percent": 51.2,
                "soil_type": "Black Cotton",
                "month": "June",
                "forecast_temp_mean_c": 30.7,
                "forecast_humidity_mean_percent": 55.0,
                "forecast_rain_mm": 620,
                "organic_carbon_percent": 0.6,
                "region": "Gujarat",
                "top_n": 3,
            }]
        },
    )

    farm_id: Optional[str] = None
    request_id: Optional[str] = Field(
        default=None,
        description="Caller-supplied id echoed back and used in the logs. "
                    "Generated when omitted.")

    # --- required sensor readings -------------------------------------
    ph: float = Field(..., description="Soil pH as reported by the sensor.", examples=[8.0])
    moisture_percent: float = Field(..., ge=0.0, le=100.0, examples=[51.2])
    soil_type: SoilType = Field(..., description="Must be one of the ten dataset classes.")
    month: Month = Field(..., description="Intended sowing month, full English name.")

    # --- EC: exactly one unit, named ----------------------------------
    ec_ds_m: Optional[float] = Field(
        default=None, description="Electrical conductivity in dS/m (e.g. 0.58).")
    ec_us_cm: Optional[float] = Field(
        default=None,
        description="Electrical conductivity in uS/cm (e.g. 580). Converted to dS/m.")

    # --- forecast over the growing window (optional, recommended) -----
    forecast_temp_mean_c: Optional[float] = Field(default=None, ge=-20.0, le=60.0)
    forecast_humidity_mean_percent: Optional[float] = Field(default=None, ge=0.0, le=100.0)
    forecast_rain_mm: Optional[float] = Field(
        default=None, ge=0.0, le=5000.0,
        description="Total rainfall over the whole growing window, not one day.")

    # --- current conditions, used only if the forecast is absent ------
    air_temp_c: Optional[float] = Field(default=None, ge=-20.0, le=60.0)
    air_humidity_percent: Optional[float] = Field(default=None, ge=0.0, le=100.0)

    organic_carbon_percent: Optional[float] = Field(default=None, ge=0.0, le=10.0)

    # --- accepted, not used by the model ------------------------------
    n_kg_ha: Optional[float] = Field(
        default=None, ge=0.0,
        description="Accepted for forward compatibility; NOT a model input.")
    p_kg_ha: Optional[float] = Field(default=None, ge=0.0, description="Not a model input.")
    k_kg_ha: Optional[float] = Field(default=None, ge=0.0, description="Not a model input.")

    previous_crops: Optional[List[str]] = Field(
        default=None, max_length=10,
        description="Crops grown on this field recently, most recent first. Used for "
                    "rotation advice only - never changes the ranking.")
    irrigation_available: Optional[bool] = Field(
        default=None,
        description="Whether the field can be irrigated. Sharpens the water-security "
                    "advice; never changes the ranking.")

    region: Optional[str] = Field(
        default=None, description="Overrides the deployed region for this call.")
    location: Optional[Location] = Field(
        default=None,
        description="Used only to fetch a forecast when temp/humidity are omitted.")
    top_n: int = Field(default=3, ge=1, le=5)

    @field_validator("soil_type", "month", mode="before")
    @classmethod
    def _normalize_enum_text(cls, v):
        """Accept any casing and stray whitespace, nothing more.

        "black cotton" and "BLACK COTTON" are the same soil class and a
        client should not have to know the table's capitalisation. An
        abbreviation like "Nov" is still rejected: it is a different value,
        not a different spelling, and guessing at it is how a field gets
        scored for the wrong season.
        """
        if not isinstance(v, str):
            return v
        cleaned = " ".join(v.split())
        for enum_cls in (SoilType, Month):
            for member in enum_cls:
                if member.value.lower() == cleaned.lower():
                    return member.value
        return cleaned

    @field_validator("ph")
    @classmethod
    def _ph_physical(cls, v: float) -> float:
        lo, hi = PH_PHYSICAL
        if not lo <= v <= hi:
            raise ValueError(
                f"pH {v} is outside the physically possible range {lo}-{hi}. "
                "Check the sensor rather than scoring this reading.")
        return v

    @model_validator(mode="after")
    def _resolve_ec(self):
        if (self.ec_ds_m is None) == (self.ec_us_cm is None):
            raise ValueError(
                "Supply electrical conductivity exactly once, in a named unit: "
                "ec_ds_m (e.g. 0.58) or ec_us_cm (e.g. 580).")
        if self.ec_us_cm is not None and self.ec_us_cm < 0:
            raise ValueError("ec_us_cm must not be negative.")
        if self.ec_ds_m is not None and self.ec_ds_m < 0:
            raise ValueError("ec_ds_m must not be negative.")
        lo, hi = EC_PHYSICAL_DS_M
        resolved = self.resolved_ec_ds_m
        if not lo <= resolved <= hi:
            raise ValueError(
                f"EC resolves to {resolved:.2f} dS/m, outside the plausible range "
                f"{lo}-{hi}. A sensor reading in uS/cm must be sent as ec_us_cm.")
        return self

    @property
    def resolved_ec_ds_m(self) -> float:
        """EC in dS/m regardless of the unit the caller used."""
        if self.ec_ds_m is not None:
            return float(self.ec_ds_m)
        return float(self.ec_us_cm) / 1000.0


class ReasonItem(BaseModel):
    """One named agronomic check behind a score. This is the useful output."""
    check: str = Field(..., examples=["pH"])
    score: float = Field(..., ge=0.0, le=1.0)
    weight: int = 0
    detail: str
    is_problem: bool = Field(
        False, description="Score below 0.5 - the thing the farmer should act on.")
    is_disqualifying: bool = Field(
        False, description="A hard veto fired: temperature, pH or EC is lethal here.")


class VarietyItem(BaseModel):
    variety: str
    score: float
    expected_yield_tha: float
    duration_days: Optional[int] = Field(
        default=None, description="Days in the field, from the variety catalogue.")
    sowing_window: Optional[str] = Field(
        default=None, description="Recommended sowing months, e.g. 'June-July'.")


class WaterSecurity(BaseModel):
    """Would rain alone have grown this crop here, season after season?

    From a daily FAO-56 soil water balance over the crop's own season in each
    of the last ten years: rain fills a root-zone bucket sized by this soil
    and this crop's rooting depth; the crop draws on it along the FAO-56 Kc
    curve. A season is adequate when rain meets >= 90 % of the need.
    """
    category: str = Field(..., description="rainfed | supplemental_irrigation | irrigation_essential")
    seasons_analysed: int
    seasons_rain_sufficient: int
    crop_water_need_mm: int
    rain_met_percent_median: int = Field(..., description="Share of need met by rain, typical year")
    rain_met_percent_dry_year: int = Field(..., description="Same, 20th-percentile (dry) year")
    typical_irrigation_mm: int = Field(..., description="Shortfall to irrigate, typical year")
    dry_year_irrigation_mm: int = Field(..., description="Shortfall to irrigate, dry year")
    root_zone_water_mm: int = Field(..., description="Plant-available water the root zone holds")
    message: str


class NutrientCheck(BaseModel):
    nutrient: str = Field(..., description="N | P | K")
    soil_kg_ha: float
    crop_range_kg_ha: List[float]
    status: str = Field(..., description="low | adequate | high")
    advice: str


class CropAgronomy(BaseModel):
    """Advice for this crop at this field. Never changes the ranking."""
    perennial: bool = False
    water_security: Optional[WaterSecurity] = None
    soil_nutrients: List[NutrientCheck] = Field(default_factory=list)
    rotation: List[str] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list, description="Plain-language summary")


class SeasonClimate(BaseModel):
    """The location's normal growing season, from its climate record."""
    years: int
    window_days: int
    rain_median_mm: float
    rain_dry_year_mm: float
    temp_mean_c: Optional[float] = None
    humidity_mean_percent: Optional[float] = None
    source: str


class CropCandidate(BaseModel):
    rank: int
    crop: str
    suitability_score: float = Field(
        ..., description="Layer 1 agronomic score 0-100. Show this one to the farmer.")
    ml_probability: float = Field(..., description="Layer 2 classifier probability.")
    confidence: float = Field(..., description="Blended score, for ranking only.")
    top_varieties: List[VarietyItem] = Field(default_factory=list)
    reasons: List[ReasonItem] = Field(default_factory=list)
    problems: List[str] = Field(
        default_factory=list, description="Details of the checks that scored below 0.5.")
    agronomy: Optional[CropAgronomy] = None


class ModelInfo(BaseModel):
    agent_id: str
    agent_version: str
    region: Optional[str] = None
    top1_accuracy: float
    top3_accuracy: float
    suitability_floor: float
    ml_weight: float


class CropPredictionResponse(BaseModel):
    """Callers must branch on `status` before reading `recommendations`."""
    status: PredictionStatus
    message: Optional[str] = Field(
        default=None,
        description="On no_suitable_crop, the text to show the farmer verbatim.")
    farm_id: Optional[str] = None
    recommendations: List[CropCandidate] = Field(default_factory=list)
    closest: Optional[CropCandidate] = Field(
        default=None,
        description="On no_suitable_crop, the nearest miss. Diagnostic only - "
                    "it is NOT a recommendation and must not be presented as one.")
    summary: Optional[str] = Field(default=None, description="Plain-text rendering.")
    narration: Optional[str] = Field(
        default=None, description="Optional LLM retelling of the reasons above.")
    warnings: List[str] = Field(default_factory=list)
    climate: Optional[SeasonClimate] = Field(
        default=None, description="Present when a location was given")
    model_info: ModelInfo
    disclaimer: str
    request_id: Optional[str] = Field(
        default=None, description="Correlates this response with the server logs.")
    cached: bool = Field(
        default=False,
        description="True when an identical field was scored recently and the "
                    "stored result was reused.")
    latency_ms: Optional[float] = Field(
        default=None, description="Server-side time spent on this request.")
    processed_at: Optional[str] = None
