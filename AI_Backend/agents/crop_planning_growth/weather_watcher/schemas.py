"""
Pydantic schemas for the Weather Watcher Agent.

Backwards-compatible:
  • The agent's run() still returns a plain dict — these schemas only
    validate it. Existing dict keys (`current_weather`, `forecast_short_term`,
    `forecast_long_term`, `alerts`, `processed_at`) are preserved.
  • New fields are additive: `rain_probability_percent`, `frost_risk`,
    `storm_warning`, `heat_stress_risk`, `agent_id`, `agent_version`.
"""

from __future__ import annotations

from datetime import date as date_t
from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


# =============================================================================
# INPUT
# =============================================================================

class Location(BaseModel):
    lat: float = Field(..., ge=-90.0, le=90.0)
    lon: float = Field(..., ge=-180.0, le=180.0)


class WeatherInput(BaseModel):
    """
    Input accepted by WeatherAgent.run().

    The agent currently also accepts a flat `{"lat": ..., "lon": ...}` dict —
    that path is preserved for the existing router/orchestrator callers.
    """
    lat: float = Field(..., ge=-90.0, le=90.0)
    lon: float = Field(..., ge=-180.0, le=180.0)
    farm_id: Optional[str] = None
    forecast_days_short: int = Field(7,  ge=1, le=7, description="OpenWeather window")
    forecast_days_long:  int = Field(14, ge=1, le=16, description="Open-Meteo window")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "lat": 23.02, "lon": 72.57,
                "farm_id": "farm-sunrise-001",
                "forecast_days_short": 7,
                "forecast_days_long": 14,
            }
        }
    )


# =============================================================================
# OUTPUT SUB-MODELS
# =============================================================================

class CurrentWeather(BaseModel):
    """Snapshot of conditions right now."""
    temperature:    float = Field(..., description="°C")
    humidity:       float = Field(..., ge=0, le=100, description="%")
    wind_speed:     float = Field(..., ge=0, description="km/h")
    conditions:     Optional[str] = Field(None, description="Clear | Clouds | Rain | Drizzle | Thunderstorm | Fog | Snow")
    rainfall_today: Optional[float] = Field(
        None, ge=0,
        description="Full-day rain total for today in mm (observed so far plus forecast). "
                    "None when no source covers today.")
    rainfall_last_hour_mm: float = Field(0.0, ge=0, description="Rain in the last hour, mm")
    source:         Optional[str] = Field(None, description="openweather | open-meteo")


class ForecastDay(BaseModel):
    """One full local calendar day."""
    date:        date_t
    temp_min:    float
    temp_max:    float
    rainfall_mm: float = Field(0.0, ge=0)
    rain_probability_percent: float = Field(0.0, ge=0, le=100)
    rain_probability_estimated: bool = Field(
        False, description="True when the provider gave no probability and it was "
                           "estimated from the rainfall amount.")
    wind_speed:  float = Field(0.0, ge=0, description="Daily maximum, km/h")
    humidity:    Optional[float] = Field(None, ge=0, le=100, description="Daily mean, %")
    source:      Optional[str] = Field(None, description="openweather | open-meteo")

    # Day-level flags read by the scheduler and irrigation planner
    frost_risk:       bool = False
    storm_warning:    bool = False
    heat_stress_risk: bool = False
    spray_unsafe:     bool = Field(False, description="Wind above the spraying limit")

    # Agrometeorology (present when the underlying data is available)
    forecast_confidence: Optional[str] = Field(
        None, description="high (days 0-2) | medium (3-6) | low (7+)")
    et0_mm: Optional[float] = Field(
        None, ge=0, description="FAO-56 Penman-Monteith reference evapotranspiration, mm")
    gdd_base10: Optional[float] = Field(None, ge=0, description="Growing degree days, base 10 C")
    leaf_wetness_hours: Optional[int] = Field(
        None, ge=0, le=24, description="Hours with RH >= 90 % or rain")
    fungal_risk: Optional[str] = Field(
        None, description="low | moderate | high - leaf wetness at 15-30 C")
    late_blight_risk: Optional[bool] = Field(
        None, description="Hutton criteria met (potato / tomato)")
    max_heat_index_c: Optional[float] = Field(None, description="NOAA heat index, C")
    heat_index_category: Optional[str] = Field(
        None, description="none | caution | extreme_caution | danger | extreme_danger")


class WeatherAlert(BaseModel):
    """Single alert triggered by current or forecast conditions."""
    type:     str = Field(..., description="heatwave | heat_stress | frost | cold_wave | "
                                           "high_wind | storm | heavy_rainfall | high_humidity")
    severity: str = Field("medium", description="low | medium | high | critical")
    message:  str
    date:     Optional[date_t] = Field(None, description="Day the alert applies to")
    source:   Optional[str] = Field(None, description="current | forecast")
    recommendations: List[str] = Field(default_factory=list)


class Location(BaseModel):
    lat: float
    lon: float


class SprayWindow(BaseModel):
    """Consecutive daylight hours fit for spraying (Delta-T, wind, rain, heat)."""
    date:           date_t
    start:          str = Field(..., description="Local time, ISO 8601")
    end:            str = Field(..., description="Local time, ISO 8601 (exclusive)")
    hours:          int
    mean_wind_kmh:  float
    mean_delta_t_c: float
    max_temp_c:     float


class WaterBalance(BaseModel):
    days:                int
    rainfall_mm:         float
    reference_et0_mm:    float
    balance_mm:          float = Field(..., description="Rain minus reference ET0")
    rain_covers_percent: Optional[int] = None
    status:              str = Field(..., description="rain_covers_demand | partly_covered | "
                                                      "irrigation_likely_needed")
    note:                str


class DrySpell(BaseModel):
    start: date_t
    end:   date_t
    days:  int


class GrowingDegreeDays(BaseModel):
    next_7_days:  float
    next_14_days: float


class AgroAdvisory(BaseModel):
    """Decisions derived from the forecast. `summary` is ready to show a farmer."""
    summary:               List[str] = Field(default_factory=list)
    water_balance_7d:      Optional[WaterBalance] = None
    gdd_base10:            Optional[GrowingDegreeDays] = None
    spray_windows:         List[SprayWindow] = Field(default_factory=list)
    spray_limiting_factor: Optional[str] = Field(
        None, description="Why no window was found, when none was")
    dry_spells:            List[DrySpell] = Field(default_factory=list)
    hourly_available:      bool = False


class WeatherWatcherOutput(BaseModel):
    """Full output of WeatherAgent.run().

    Check `status` before acting: `unavailable` means there is no weather
    data in this response at all.
    """
    agent_id:      str = "weather_agent"
    agent_version: str = "3.0.0"
    processed_at:  Optional[str] = None

    status:   str = Field("ok", description="ok | partial | unavailable")
    location: Optional[Location] = None
    timezone: Optional[str] = Field(None, description="Farm's timezone, e.g. Asia/Kolkata")

    current_weather:     Optional[CurrentWeather] = None
    forecast_short_term: List[ForecastDay] = Field(default_factory=list, description="Today and the next 6 days")
    forecast_long_term:  List[ForecastDay] = Field(default_factory=list, description="Days 8-14")
    alerts:              List[WeatherAlert] = Field(default_factory=list)
    agro_advisory:       Optional[AgroAdvisory] = None
    utc_offset_seconds:  Optional[int] = None

    sources:  Dict[str, str] = Field(default_factory=dict, description="Per-provider: ok | failed | skipped")
    warnings: List[str] = Field(default_factory=list)
    fetched_at: Optional[str] = Field(None, description="When the providers were queried (UTC)")
    cached: bool = False
    data_age_seconds: int = 0
