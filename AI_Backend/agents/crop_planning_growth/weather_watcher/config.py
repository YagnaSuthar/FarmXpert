"""
Weather Watcher Agent — Configuration
======================================
External endpoints, operational limits and alert thresholds.

Operational settings can be overridden per deployment with FARMXPERT_WX_*
environment variables. Alert thresholds cannot: they follow published
definitions (India Meteorological Department where one exists) so that an
alert means the same thing to every farmer, and changing one changes what
the agent tells people about danger to their crop.
"""

from __future__ import annotations

import os
from typing import Final


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


# ── Agent identity ──────────────────────────────────────────────────────────

AGENT_ID:      Final[str] = "weather_agent"
AGENT_VERSION: Final[str] = "3.0.0"
AGENT_NAME:    Final[str] = "Weather Watcher"


# ── External APIs ───────────────────────────────────────────────────────────

OPENWEATHER_BASE_URL: Final[str] = os.getenv(
    "FARMXPERT_WX_OPENWEATHER_URL",
    "https://api.openweathermap.org/data/2.5",
)
OPENMETEO_BASE_URL: Final[str] = os.getenv(
    "FARMXPERT_WX_OPENMETEO_URL",
    "https://api.open-meteo.com/v1/forecast",
)

# Per-attempt timeout. Short enough that a hung provider cannot stall a
# farmer's request; the retry below covers a single slow response.
HTTP_TIMEOUT_SECONDS: Final[float] = _env_float("FARMXPERT_WX_TIMEOUT", 8.0)

# Retries for transient failures only (timeouts, connection errors, 429,
# 5xx). A 4xx such as a bad API key is never retried - it cannot succeed.
HTTP_MAX_RETRIES: Final[int] = _env_int("FARMXPERT_WX_RETRIES", 2)
HTTP_BACKOFF_SECONDS: Final[float] = _env_float("FARMXPERT_WX_BACKOFF", 0.5)


# ── Caching ─────────────────────────────────────────────────────────────────

# Forecasts update a few times a day; fetching per request only spends the
# provider quota (OpenWeather free tier: 60 calls/min) three times over,
# because the crop, irrigation and weather agents all ask for the same farm.
CACHE_TTL_SECONDS: Final[float] = _env_float("FARMXPERT_WX_CACHE_TTL", 900.0)
# When every provider is down, an older forecast is far more useful to a
# farmer than nothing - served with a warning saying how old it is.
CACHE_STALE_MAX_SECONDS: Final[float] = _env_float("FARMXPERT_WX_STALE_MAX", 6 * 3600.0)
CACHE_MAX_ENTRIES: Final[int] = _env_int("FARMXPERT_WX_CACHE_SIZE", 2048)
# Coordinates are rounded to this many decimals for the cache key.
# 2 decimals is ~1.1 km: the same farm, and finer than any forecast grid.
CACHE_COORD_DECIMALS: Final[int] = 2


# ── Forecast windows ────────────────────────────────────────────────────────

# Days 0-6 are "short term", the rest "long term". Open-Meteo covers up to 16.
SHORT_TERM_DAYS: Final[int] = 7
LONG_RANGE_DAYS: Final[int] = 14

# A 3-hourly OpenWeather day is used only when it is complete enough to be a
# real daily aggregate; otherwise Open-Meteo's full-day values are used.
MIN_SLOTS_FOR_FULL_DAY: Final[int] = 7   # of 8 three-hour slots


# ── Alert thresholds ────────────────────────────────────────────────────────
#
# Sources:
#   IMD heat wave (plains): Tmax >= 45 C is a heat wave on the absolute
#     criterion, >= 47 C a severe heat wave. IMD's other criterion needs the
#     departure from the station's climatological normal, which this agent
#     does not have - so 40-45 C is reported as "heat_stress", not as a
#     heat wave, rather than overstating it.
#   IMD cold wave (plains): Tmin <= 4 C.
#   Frost: ground frost is likely when screen-level Tmin falls to ~2 C
#     (the ground runs a few degrees colder than the air at 2 m).
#   IMD rainfall categories (24 h): heavy 64.5-115.5 mm, very heavy
#     115.6-204.4 mm, extremely heavy >= 204.5 mm.
#   Wind (Beaufort): force 6 "strong wind" >= 39 km/h, force 8 "gale"
#     >= 62 km/h.
#   Humidity: a daily mean >= 85 % is the usual trigger for fungal disease
#     risk advisories.

ALERT_THRESHOLDS = {
    # Heat - daily maximum air temperature, C
    "heat_stress_temp_c":        40.0,
    "heatwave_temp_c":           45.0,
    "severe_heatwave_temp_c":    47.0,

    # Cold - daily minimum air temperature, C
    "cold_wave_temp_c":           4.0,
    "frost_temp_c":               2.0,
    "hard_frost_temp_c":          0.0,

    # Rain - mm per day
    "heavy_rainfall_mm":         64.5,
    "very_heavy_rainfall_mm":   115.6,
    "extreme_rainfall_mm":      204.5,

    # Wind - km/h
    "spray_wind_limit_kmh":      15.0,    # scheduler uses the same value
    "strong_wind_kmh":           39.0,
    "gale_wind_kmh":             62.0,

    # Humidity - daily mean %
    "high_humidity_percent":     85.0,
}


# ── Agrometeorology ─────────────────────────────────────────────────────────
#
# Each constant names its source. These turn a forecast into the decisions a
# farmer actually makes: whether to irrigate, when to spray, when to scout
# for disease, when the field is dry enough to work.

AGROMET = {
    # Growing degree days, simple average method: max(0, (Tmax+Tmin)/2 - base).
    # 10 C is the conventional general-purpose base; crop-specific bases
    # differ (cotton ~15.5 C) and belong to a crop model.
    "gdd_base_c": 10.0,

    # Spray windows (GRDC "Spray application manual"; standard extension
    # guidance). Delta-T = dry-bulb minus wet-bulb temperature.
    "spray_delta_t_min_c": 2.0,     # below: droplets persist, drift at inversion
    "spray_delta_t_max_c": 8.0,     # above: fine droplets evaporate before landing
    "spray_wind_min_kmh": 3.0,      # below: surface inversions, drift of fine droplets
    "spray_wind_max_kmh": 15.0,     # above: drift
    "spray_temp_max_c": 30.0,       # above: evaporation and volatilisation losses
    "spray_temp_min_c": 5.0,        # below: poor uptake; frost / ice on foliage
    "frozen_ground_tmax_c": 2.0,    # daytime max at or below: soil stays frozen
    "spray_rain_free_hours": 4,     # rainfastness margin after application
    "spray_rain_prob_max": 30.0,    # % in the spraying hour
    "spray_min_window_hours": 2,
    "spray_horizon_hours": 72,

    # Leaf wetness proxy: hours with RH >= 90 % ("NHRH" method). Most foliar
    # fungi infect when leaves stay wet >= 6 h at 15-30 C.
    "leaf_wet_rh": 90.0,
    "fungal_temp_min_c": 15.0,
    "fungal_temp_max_c": 30.0,
    "fungal_moderate_hours": 6,
    "fungal_high_hours": 10,

    # Potato / tomato late blight - Hutton criteria (AHDB, 2017): two
    # consecutive days each with Tmin >= 10 C and >= 6 h of RH >= 90 %.
    "hutton_tmin_c": 10.0,
    "hutton_humid_hours": 6,
    "hutton_rh": 90.0,

    # Water balance over the short-term window: rain as a share of FAO-56
    # reference evapotranspiration.
    "water_covered_ratio": 1.0,
    "water_partial_ratio": 0.5,

    # Dry spell for field work / harvest.
    "dry_day_rain_mm": 1.0,
    "dry_day_rain_prob": 40.0,
    "dry_spell_min_days": 2,

    # NOAA heat index categories, C (converted from the NWS F bands).
    "heat_index_caution_c": 26.7,
    "heat_index_extreme_caution_c": 32.2,
    "heat_index_danger_c": 39.4,
    "heat_index_extreme_danger_c": 51.7,

    # Forecast skill falls with lead time: days 0-2 high, 3-6 medium, 7+ low.
    "confidence_high_days": 3,
    "confidence_medium_days": 7,
}


# ── Sanity bounds for provider data ─────────────────────────────────────────
# A provider occasionally returns a corrupt value. Days outside these bounds
# are dropped with a warning instead of reaching a farmer as fact.

VALID_TEMP_C: Final[tuple] = (-60.0, 60.0)
VALID_RAIN_MM: Final[tuple] = (0.0, 1000.0)
VALID_WIND_KMH: Final[tuple] = (0.0, 400.0)


# ── Unit conversions ────────────────────────────────────────────────────────

MS_TO_KMH: Final[float] = 3.6   # OpenWeather metric wind is m/s
