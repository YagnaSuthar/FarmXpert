"""
Root-zone soil water balance — FAO-56 chapter 8, as pure functions.

The state is the root-zone depletion Dr (mm below field capacity):
  • TAW = 1000 (θfc − θwp) Zr     total available water       (FAO-56 eq. 82)
  • RAW = p · TAW                 readily available water     (eq. 83)
    p adjusted for evaporative demand: p = p_tab + 0.04 (5 − ETc)
  • Ks  = (TAW − Dr) / ((1 − p) TAW) when Dr > RAW, else 1     (eq. 84)
  • Dr,i = Dr,i−1 − P_eff − I + Ks·ETc, kept within [0, TAW]   (eq. 85)
    Water pushing Dr below 0 is deep percolation - it drains only from a
    soil wetter than field capacity, never from a drying one.

Plus ET₀ by Hargreaves–Samani (eq. 52) when no Penman–Monteith value is
available, crop salt tolerance (Maas & Hoffman) and the FAO-29 leaching
requirement. Nothing here does I/O.
"""
from __future__ import annotations

import math
from datetime import date
from typing import Optional

from AI_Backend.agents.crop_planning_growth.irrigation_planner.config import (
    MAX_THETA_ABOVE_FC,
    RAIN_EFFECTIVE_FRACTION,
    RAIN_RUNOFF_ABOVE_MM,
    STAGE_SHARES,
)


# ── Water holding ──────────────────────────────────────────────────────────

def total_available_water(theta_fc: float, theta_wp: float, root_depth_m: float) -> float:
    return 1000.0 * (theta_fc - theta_wp) * root_depth_m


def depletion_fraction(p_table: float, etc_mm: float) -> float:
    """FAO-56 Table 22 p, adjusted for the day's ETc and kept in 0.1-0.8."""
    return min(0.8, max(0.1, p_table + 0.04 * (5.0 - etc_mm)))


def depletion_from_sensor(theta_percent: float, theta_fc: float, theta_wp: float,
                          root_depth_m: float) -> tuple[Optional[float], Optional[str]]:
    """Root-zone depletion (mm) from a volumetric moisture reading.

    Accepts percent (32) or fraction (0.32). Returns (depletion, problem):
    a reading far above field capacity is saturated or faulty, and a
    reading below the wilting point is clipped to it.
    """
    theta = theta_percent / 100.0 if theta_percent > 1.0 else theta_percent
    if theta < 0 or theta > theta_fc + MAX_THETA_ABOVE_FC:
        return None, (f"Soil moisture reading {theta_percent} is outside the plausible range "
                      "for this soil and was ignored - check the sensor.")
    taw = total_available_water(theta_fc, theta_wp, root_depth_m)
    depletion = 1000.0 * (theta_fc - theta) * root_depth_m
    return min(taw, max(0.0, depletion)), None


def stress_coefficient(depletion: float, taw: float, p: float) -> float:
    raw = p * taw
    if depletion <= raw or taw <= 0:
        return 1.0
    return max(0.0, (taw - depletion) / ((1.0 - p) * taw))


# ── Rain ───────────────────────────────────────────────────────────────────

def effective_rain(rain_mm: float, probability_percent: Optional[float]) -> float:
    """Rain expected to enter the root zone.

    Probability-weighted (a 30 % chance of 20 mm is worth 6 mm, not 20),
    then the CROPWAT fixed-percentage rule, with half of anything above
    50 mm/day lost to runoff.
    """
    if rain_mm <= 0:
        return 0.0
    expected = rain_mm * (min(100.0, max(0.0, probability_percent)) / 100.0
                          if probability_percent is not None else 1.0)
    first = min(expected, RAIN_RUNOFF_ABOVE_MM)
    excess = max(0.0, expected - RAIN_RUNOFF_ABOVE_MM)
    return RAIN_EFFECTIVE_FRACTION * first + 0.5 * RAIN_EFFECTIVE_FRACTION * excess


# ── Evapotranspiration ─────────────────────────────────────────────────────

def extraterrestrial_radiation(lat_deg: float, day: date) -> float:
    """Ra in MJ m-2 day-1 (FAO-56 eq. 21-25). FAO Example 8: 20°S, 3 Sep -> 32.2."""
    j = day.timetuple().tm_yday
    phi = math.radians(lat_deg)
    dr = 1 + 0.033 * math.cos(2 * math.pi * j / 365)
    delta = 0.409 * math.sin(2 * math.pi * j / 365 - 1.39)
    ws = math.acos(max(-1.0, min(1.0, -math.tan(phi) * math.tan(delta))))
    return (24 * 60 / math.pi) * 0.0820 * dr * (
        ws * math.sin(phi) * math.sin(delta) + math.cos(phi) * math.cos(delta) * math.sin(ws))


def et0_hargreaves(temp_min: float, temp_max: float, lat_deg: float, day: date) -> float:
    """Hargreaves-Samani ET₀, mm/day (FAO-56 eq. 52) - the temperature-only fallback."""
    ra_mm = 0.408 * extraterrestrial_radiation(lat_deg, day)
    t_mean = (temp_min + temp_max) / 2.0
    return max(0.0, 0.0023 * (t_mean + 17.8) * math.sqrt(max(0.0, temp_max - temp_min)) * ra_mm)


# ── Salinity ───────────────────────────────────────────────────────────────

def relative_yield_percent(ece: float, threshold: float, slope: float) -> float:
    """Maas-Hoffman: 100 % up to the threshold, then minus `slope` % per dS/m."""
    return max(0.0, min(100.0, 100.0 - slope * max(0.0, ece - threshold)))


def leaching_requirement(ec_water: float, ece_threshold: float) -> Optional[float]:
    """FAO-29 (Rhoades): LR = ECw / (5 ECe_threshold − ECw). None if water too saline."""
    denominator = 5.0 * ece_threshold - ec_water
    if ec_water <= 0 or denominator <= 0:
        return None
    return min(0.5, ec_water / denominator)


# ── Growth stage ───────────────────────────────────────────────────────────

def stage_from_days(days_after_sowing: int, season_days: int) -> str:
    """Map days after sowing onto a named stage using FAO-56 stage shares."""
    ini, dev, mid, _late = STAGE_SHARES
    f = max(0.0, days_after_sowing) / max(1, season_days)
    if days_after_sowing < 7 and f < ini:
        return "germination"
    if f < ini:
        return "seedling"
    if f < ini + dev:
        return "vegetative"
    if f < ini + dev + mid / 2:
        return "flowering"
    if f < ini + dev + mid:
        return "fruiting"
    if f < 0.95:
        return "maturation"
    return "harvest_ready"
