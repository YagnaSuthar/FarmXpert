# =============================================================================
# config.py — Soil Health Agent Configuration
# =============================================================================
# Every table here is read by service.py. Each value names its basis.
#
# CALIBRATION HISTORY
#   v1.0.0  Used fertilizer-dose values as soil-test ranges.
#   v2.0.0  Nutrient ranges moved to soil-test norms (mineral-N, Olsen-P,
#           NH4OAc-K); alert penalties rebalanced.
#   v2.1.0  Indian field calibration (K min 60, temp max 35, EC max 1.8).
#   v3.0.0  Moisture judged as plant-available water for the soil type (the
#           old 40-70 % "optimal" band called a sandy field at field capacity
#           critically dry); crop salt tolerance from Maas-Hoffman; 7 crops
#           added; sodicity and legume-nitrogen advice corrected; the seasonal
#           score multiplier removed; configuration nothing read removed.
#
# NUTRIENT BASIS (what the sensor numbers are taken to mean)
#   Nitrogen   mg/kg mineral N (NO3-N + NH4-N) - the pool an in-field sensor
#              estimates. NOT the alkaline-KMnO4 "available N" of the Soil
#              Health Card (kg/ha), which is a different test and 5-10x larger.
#   Phosphorus mg/kg Olsen-P (international sufficiency ~10-25 mg/kg).
#   Potassium  mg/kg NH4OAc-K; ICAR low <108 kg/ha = ~55 mg/kg, medium to 280
#              kg/ha = ~140 mg/kg.
#   EC         dS/m, read as saturated-paste ECe. In-field probes read bulk EC,
#              usually lower - confirm salinity with a lab ECe test.
#
# SOURCES
#   FAO-56 (Allen et al., 1998) Tables 19 and 22 - soil water, depletion p.
#   Maas & Hoffman (1977), Maas (1984) - crop salt tolerance.
#   ICAR soil-test ratings; USDA salinity classes; ICAR sodic-soil reclamation
#   (gypsum on gypsum-requirement basis).
# =============================================================================

from __future__ import annotations

from typing import Any

# Soil water properties and FAO-56 depletion fractions are owned by the
# irrigation planner. Reading them here keeps one set of numbers for both
# agents, so "dry" means the same thing to each.
from AI_Backend.agents.crop_planning_growth.irrigation_planner.config import (
    CROP_ALIASES as _IRRIGATION_CROP_ALIASES,
    CROP_CONFIG as _IRRIGATION_CROPS,
    SOIL_ALIASES as _IRRIGATION_SOIL_ALIASES,
    SOIL_CONFIG as SOIL_HYDRAULICS,
)

# =============================================================================
# SECTION 1 — AGENT IDENTITY
# =============================================================================

AGENT_ID      = "soil_health_agent"
AGENT_VERSION = "3.0.0"
AGENT_NAME    = "Soil Health Monitor"

# =============================================================================
# SECTION 2 — VALIDATION (physically plausible sensor ranges)
# =============================================================================

VALID_RANGES: dict[str, dict[str, float]] = {
    "moisture":        {"min": 0.0,   "max": 70.0},    # volumetric %; above ~70 is not soil
    "temperature":     {"min": -10.0, "max": 60.0},
    "ph":              {"min": 3.0,   "max": 10.0},
    "nitrogen":        {"min": 0.0,   "max": 500.0},
    "phosphorus":      {"min": 0.0,   "max": 200.0},
    "potassium":       {"min": 0.0,   "max": 800.0},
    "ec":              {"min": 0.0,   "max": 16.0},
    "air_temperature": {"min": -20.0, "max": 55.0},
    "humidity":        {"min": 0.0,   "max": 100.0},
    "rainfall":        {"min": 0.0,   "max": 500.0},
}

# =============================================================================
# SECTION 3 — GLOBAL OPTIMAL RANGES (used when the crop is unknown)
# =============================================================================
# Moisture is not here: it is judged per soil type as plant-available water
# (Section 6), because the same 25 % reading is field capacity on a loam and
# near wilting on a clay.

GLOBAL_OPTIMAL_RANGES: dict[str, dict[str, float]] = {
    "temperature":     {"min": 12.0,  "max": 35.0},
    "ph":              {"min": 6.0,   "max": 7.5},
    "nitrogen":        {"min": 30.0,  "max": 90.0},
    "phosphorus":      {"min": 10.0,  "max": 28.0},
    "potassium":       {"min": 60.0,  "max": 160.0},
    "ec":              {"min": 0.2,   "max": 1.8},
    "air_temperature": {"min": 15.0,  "max": 35.0},
    "humidity":        {"min": 40.0,  "max": 80.0},
}

# =============================================================================
# SECTION 4 — ALERT THRESHOLDS (risk, not mild deviation from "best")
# =============================================================================

ALERT_THRESHOLDS: dict[str, dict[str, float]] = {
    # Below ~5 C roots and soil microbes are barely active; the critical
    # threshold (2 C) marks near-frozen soil.
    "temperature": {"low": 5.0, "high": 35.0},
    "ec":          {"high": 2.0},     # above the USDA non-saline class
    "ph":          {"low": 5.5, "high": 8.5},
    "nitrogen":    {"low": 25.0, "high": 120.0},
    "phosphorus":  {"low": 8.0,  "high": 45.0},
    "potassium":   {"low": 55.0, "high": 220.0},
}

NITROGEN_THRESHOLDS: dict[str, float] = {
    "optimal_max": 90.0,
    "medium":      120.0,
    "high":        180.0,
    "critical":    220.0,
}

# =============================================================================
# SECTION 5 — CROPS
# =============================================================================
# optimal_ranges  score bands per parameter (moisture: see Section 6)
# legume          fixes its own nitrogen - low soil N calls for Rhizobium and a
#                 starter dose, not a full urea programme
# salinity        Maas-Hoffman: yield holds to `threshold` dS/m ECe, then falls
#                 `slope` % per dS/m; None where no published value exists
# crop_advice     crop-specific nutrition practice surfaced as suggestions
# =============================================================================

CROP_CONFIG: dict[str, dict[str, Any]] = {

    "wheat": {
        "display_name": "Wheat",
        "optimal_ranges": {
            "temperature": {"min": 10.0, "max": 25.0},
            "ph":          {"min": 6.0,  "max": 7.5},
            "nitrogen":    {"min": 30.0, "max": 90.0},
            "phosphorus":  {"min": 10.0, "max": 25.0},
            "potassium":   {"min": 60.0, "max": 150.0},
            "ec":          {"min": 0.2,  "max": 2.2},
        },
        "legume": False,
        "salinity": {"threshold": 6.0, "slope": 7.1},
        "crop_advice": ["Split nitrogen: half at sowing, the rest at crown-root initiation "
                        "(~21 days) and tillering.",
                        "Zinc sulphate 25 kg/ha on zinc-deficient soils."],
    },

    "rice": {
        "display_name": "Rice (Paddy)",
        "optimal_ranges": {
            "temperature": {"min": 22.0, "max": 35.0},
            "ph":          {"min": 5.5,  "max": 7.0},
            "nitrogen":    {"min": 25.0, "max": 80.0},
            "phosphorus":  {"min": 8.0,  "max": 22.0},
            "potassium":   {"min": 55.0, "max": 140.0},
            "ec":          {"min": 0.1,  "max": 1.5},
        },
        "legume": False,
        "paddy": True,
        "salinity": {"threshold": 3.0, "slope": 12.0},
        "crop_advice": ["Zinc deficiency (khaira) is common in flooded rice - zinc sulphate "
                        "25 kg/ha at puddling.",
                        "Place urea in the reduced layer or use deep placement to cut losses."],
    },

    "maize": {
        "display_name": "Maize",
        "optimal_ranges": {
            "temperature": {"min": 18.0, "max": 35.0},
            "ph":          {"min": 5.8,  "max": 7.0},
            "nitrogen":    {"min": 35.0, "max": 90.0},
            "phosphorus":  {"min": 12.0, "max": 28.0},
            "potassium":   {"min": 65.0, "max": 160.0},
            "ec":          {"min": 0.2,  "max": 1.7},
        },
        "legume": False,
        "salinity": {"threshold": 1.7, "slope": 12.0},
        "crop_advice": ["Heavy nitrogen feeder: split N at sowing, knee-high and tasselling.",
                        "Zinc deficiency (white bud) on calcareous soils - zinc sulphate 25 kg/ha."],
    },

    "cotton": {
        "display_name": "Cotton",
        "optimal_ranges": {
            "temperature": {"min": 22.0, "max": 38.0},
            "ph":          {"min": 6.0,  "max": 8.0},
            "nitrogen":    {"min": 25.0, "max": 80.0},
            "phosphorus":  {"min": 8.0,  "max": 22.0},
            "potassium":   {"min": 90.0, "max": 190.0},
            "ec":          {"min": 0.2,  "max": 2.5},
        },
        "legume": False,
        "salinity": {"threshold": 7.7, "slope": 5.2},
        "crop_advice": ["Potassium drives boll weight and fibre quality - do not let K fall "
                        "below range at flowering.",
                        "Excess nitrogen causes rank vegetative growth and boll shedding.",
                        "Boron foliar spray at squaring helps boll retention on B-poor soils."],
    },

    "sugarcane": {
        "display_name": "Sugarcane",
        "optimal_ranges": {
            "temperature": {"min": 25.0, "max": 38.0},
            "ph":          {"min": 6.0,  "max": 7.5},
            "nitrogen":    {"min": 40.0, "max": 100.0},
            "phosphorus":  {"min": 10.0, "max": 25.0},
            "potassium":   {"min": 90.0, "max": 190.0},
            "ec":          {"min": 0.2,  "max": 1.7},
        },
        "legume": False,
        "salinity": {"threshold": 1.7, "slope": 5.9},
        "crop_advice": ["Long season: split N and K into 3-4 doses through the grand growth phase."],
    },

    "soybean": {
        "display_name": "Soybean",
        "optimal_ranges": {
            "temperature": {"min": 18.0, "max": 32.0},
            "ph":          {"min": 6.0,  "max": 7.0},
            "nitrogen":    {"min": 15.0, "max": 60.0},
            "phosphorus":  {"min": 10.0, "max": 28.0},
            "potassium":   {"min": 60.0, "max": 150.0},
            "ec":          {"min": 0.1,  "max": 1.5},
        },
        "legume": True,
        "salinity": {"threshold": 5.0, "slope": 20.0},
        "crop_advice": ["Inoculate seed with Bradyrhizobium; nodulation needs pH 6.0-7.0.",
                        "Sulphur 20-30 kg/ha improves oil and protein."],
    },

    "potato": {
        "display_name": "Potato",
        "optimal_ranges": {
            "temperature": {"min": 10.0, "max": 20.0},
            "ph":          {"min": 5.0,  "max": 6.5},
            "nitrogen":    {"min": 28.0, "max": 85.0},
            "phosphorus":  {"min": 12.0, "max": 30.0},
            "potassium":   {"min": 90.0, "max": 195.0},
            "ec":          {"min": 0.1,  "max": 1.5},
        },
        "legume": False,
        "salinity": {"threshold": 1.7, "slope": 12.0},
        "crop_advice": ["Keep pH below 6.5 to limit common scab.",
                        "High potassium demand for tuber bulking; sulphate of potash improves "
                        "tuber quality."],
    },

    "tomato": {
        "display_name": "Tomato",
        "optimal_ranges": {
            "temperature": {"min": 18.0, "max": 30.0},
            "ph":          {"min": 6.0,  "max": 7.0},
            "nitrogen":    {"min": 30.0, "max": 90.0},
            "phosphorus":  {"min": 15.0, "max": 30.0},
            "potassium":   {"min": 90.0, "max": 190.0},
            "ec":          {"min": 0.2,  "max": 2.0},
        },
        "legume": False,
        "salinity": {"threshold": 2.5, "slope": 9.9},
        "crop_advice": ["Blossom-end rot is calcium failing to reach the fruit, usually from "
                        "irregular watering - keep soil moisture even.",
                        "Boron 1-2 kg/ha on B-poor soils improves fruit set."],
    },

    "groundnut": {
        "display_name": "Groundnut",
        "optimal_ranges": {
            "temperature": {"min": 20.0, "max": 35.0},
            "ph":          {"min": 6.0,  "max": 7.5},
            "nitrogen":    {"min": 15.0, "max": 60.0},
            "phosphorus":  {"min": 12.0, "max": 28.0},
            "potassium":   {"min": 60.0, "max": 150.0},
            "ec":          {"min": 0.1,  "max": 2.0},
        },
        "legume": True,
        "salinity": {"threshold": 3.2, "slope": 29.0},
        "crop_advice": ["Gypsum 500 kg/ha at pegging (30-40 days) supplies the calcium and "
                        "sulphur pods need - unfilled pods (pops) follow calcium shortage.",
                        "Inoculate seed with Rhizobium; zinc sulphate 25 kg/ha on calcareous soils."],
    },

    "guar": {
        "display_name": "Guar (Cluster Bean)",
        "optimal_ranges": {
            "temperature": {"min": 20.0, "max": 38.0},
            "ph":          {"min": 7.0,  "max": 8.5},
            "nitrogen":    {"min": 15.0, "max": 60.0},
            "phosphorus":  {"min": 10.0, "max": 25.0},
            "potassium":   {"min": 55.0, "max": 140.0},
            "ec":          {"min": 0.1,  "max": 3.0},
        },
        "legume": True,
        "salinity": {"threshold": 8.8, "slope": 17.0},
        "crop_advice": ["Responds strongly to phosphorus (40 kg P2O5/ha) and Rhizobium "
                        "inoculation; needs little nitrogen."],
    },

    "white peas": {
        "display_name": "White Peas",
        "optimal_ranges": {
            "temperature": {"min": 10.0, "max": 25.0},
            "ph":          {"min": 6.0,  "max": 7.5},
            "nitrogen":    {"min": 15.0, "max": 60.0},
            "phosphorus":  {"min": 12.0, "max": 28.0},
            "potassium":   {"min": 60.0, "max": 150.0},
            "ec":          {"min": 0.1,  "max": 1.5},
        },
        "legume": True,
        "salinity": {"threshold": 3.4, "slope": 10.6},
        "crop_advice": ["Inoculate with Rhizobium; a 20 kg N/ha starter is enough."],
    },

    "coriander": {
        "display_name": "Coriander",
        "optimal_ranges": {
            "temperature": {"min": 15.0, "max": 28.0},
            "ph":          {"min": 6.0,  "max": 8.0},
            "nitrogen":    {"min": 25.0, "max": 80.0},
            "phosphorus":  {"min": 10.0, "max": 25.0},
            "potassium":   {"min": 60.0, "max": 150.0},
            "ec":          {"min": 0.1,  "max": 1.5},
        },
        "legume": False,
        "salinity": None,
        "crop_advice": ["Leafy harvests respond to nitrogen - split into two light doses."],
    },

    "ajwain": {
        "display_name": "Ajwain",
        "optimal_ranges": {
            "temperature": {"min": 15.0, "max": 30.0},
            "ph":          {"min": 6.5,  "max": 8.2},
            "nitrogen":    {"min": 25.0, "max": 80.0},
            "phosphorus":  {"min": 10.0, "max": 25.0},
            "potassium":   {"min": 60.0, "max": 150.0},
            "ec":          {"min": 0.1,  "max": 2.0},
        },
        "legume": False,
        "salinity": None,
        "crop_advice": ["Moderate nutrient demand; excess nitrogen delays maturity and "
                        "lowers seed oil."],
    },

    "cabbage": {
        "display_name": "Cabbage",
        "optimal_ranges": {
            "temperature": {"min": 15.0, "max": 25.0},
            "ph":          {"min": 6.0,  "max": 7.5},
            "nitrogen":    {"min": 30.0, "max": 90.0},
            "phosphorus":  {"min": 12.0, "max": 28.0},
            "potassium":   {"min": 80.0, "max": 180.0},
            "ec":          {"min": 0.2,  "max": 1.8},
        },
        "legume": False,
        "salinity": {"threshold": 1.8, "slope": 9.7},
        "crop_advice": ["Boron deficiency causes hollow stems, and molybdenum deficiency causes "
                        "whiptail on acid soils - lime acid soils and apply borax 10 kg/ha.",
                        "Club root thrives in acid soil; liming to pH 7 suppresses it."],
    },

    "mango": {
        "display_name": "Mango (orchard)",
        "optimal_ranges": {
            "temperature": {"min": 20.0, "max": 38.0},
            "ph":          {"min": 5.5,  "max": 7.5},
            "nitrogen":    {"min": 30.0, "max": 90.0},
            "phosphorus":  {"min": 10.0, "max": 25.0},
            "potassium":   {"min": 80.0, "max": 180.0},
            "ec":          {"min": 0.1,  "max": 1.5},
        },
        "legume": False,
        "salinity": None,
        "crop_advice": ["Manure and fertilise after harvest, in the tree's feeding zone "
                        "(canopy drip line), not at the trunk.",
                        "Zinc and boron sprays before flowering reduce fruit drop."],
    },
}

# Names callers use for the same crops (crop-prediction and irrigation names too).
CROP_ALIASES: dict[str, str] = {
    **_IRRIGATION_CROP_ALIASES,
    "coriander (leaves)": "coriander", "groundnuts": "groundnut",
}

# =============================================================================
# SECTION 6 — SOIL TYPES
# =============================================================================
# score_modifiers: how much each parameter matters on this soil. Water
# properties (field capacity, wilting point) come from SOIL_HYDRAULICS.
# =============================================================================

SOIL_TYPE_CONFIG: dict[str, dict[str, Any]] = {
    "sandy": {
        "display_name": "Sandy",
        "score_modifiers": {"moisture": 1.25, "nitrogen": 1.20, "phosphorus": 1.10, "ec": 0.90},
        "notes": "Low CEC - nitrogen and potassium leach quickly; split fertilizer doses.",
    },
    "sandy_loam": {
        "display_name": "Sandy Loam",
        "score_modifiers": {"moisture": 1.15, "nitrogen": 1.10},
        "notes": "Light soil - moderate leaching; split nitrogen.",
    },
    "loamy": {
        "display_name": "Loam",
        "score_modifiers": {},
        "notes": "Reference soil - balanced retention and drainage.",
    },
    "silt": {
        "display_name": "Silt / Silty Loam",
        "score_modifiers": {"moisture": 1.10, "ec": 1.10, "phosphorus": 0.95},
        "notes": "Crusts easily; moderate fertility.",
    },
    "clay_loam": {
        "display_name": "Clay Loam",
        "score_modifiers": {"moisture": 1.15, "ec": 1.10},
        "notes": "Good retention; watch drainage.",
    },
    "clay": {
        "display_name": "Clay",
        "score_modifiers": {"moisture": 1.30, "ec": 1.20, "nitrogen": 0.90, "ph": 1.15},
        "notes": "High CEC; waterlogging and compaction risk; salts accumulate without drainage.",
    },
    "black_cotton": {
        "display_name": "Black Cotton (Vertisol)",
        "score_modifiers": {"moisture": 1.25, "ec": 1.20, "ph": 1.10, "potassium": 0.85},
        "notes": "Naturally rich in potassium; alkaline and often calcareous - zinc and iron "
                 "availability is low. Poor internal drainage lets salts build up.",
    },
    "alluvial": {
        "display_name": "Alluvial",
        "score_modifiers": {},
        "notes": "Productive, well-drained; nitrogen is usually the limiting nutrient.",
    },
    "red_laterite": {
        "display_name": "Red Laterite",
        "score_modifiers": {"ph": 1.20, "phosphorus": 1.15, "moisture": 1.15},
        "notes": "Acidic and low in phosphorus availability (iron and aluminium fix P); "
                 "liming and organic matter help.",
    },
    "peaty": {
        "display_name": "Peaty",
        "score_modifiers": {"ph": 1.40, "moisture": 1.35, "nitrogen": 0.85, "ec": 0.80},
        "notes": "High organic matter; acidic; lime regularly; drainage matters most.",
    },
}

SOIL_ALIASES: dict[str, str] = {**_IRRIGATION_SOIL_ALIASES, "loam": "loamy"}

# Soil the moisture reading is interpreted against when none is given.
DEFAULT_SOIL_FOR_MOISTURE = "loamy"

# Moisture as plant-available water (AW):
#   AW % = (θ − θwp) / (θfc − θwp) × 100   (0 = wilting point, 100 = field capacity)
# Stress begins once AW falls below (1 − p) × 100, where p is the crop's FAO-56
# depletion fraction (0.5 when the crop is unknown).
MOISTURE_RULES: dict[str, float] = {
    "default_p":               0.50,
    "critical_low_aw":         10.0,    # close to wilting
    "high_above_fc":           0.05,    # θ this far above field capacity: waterlogging onset
    "critical_high_above_fc":  0.12,    # near saturation
    "paddy_low_aw":            100.0,   # flooded rice wants the soil at/above capacity
    "paddy_critical_low_aw":   50.0,
}

# =============================================================================
# SECTION 7 — WEATHER RULES (in-field air sensors)
# =============================================================================

WEATHER_IMPACT_RULES: dict[str, dict[str, Any]] = {
    "high_temperature": {"parameter": "air_temperature", "direction": "above",
                         "threshold": 38.0, "critical_threshold": 45.0,
                         "alert_code": "HEAT_STRESS", "severity": "high"},
    "low_temperature":  {"parameter": "air_temperature", "direction": "below",
                         "threshold": 5.0, "critical_threshold": -2.0,
                         "alert_code": "FROST_RISK", "severity": "high"},
    "low_rainfall":     {"parameter": "rainfall", "direction": "below",
                         "threshold": 5.0, "critical_threshold": 0.0,
                         "alert_code": "DROUGHT_RISK", "severity": "medium"},
    "high_rainfall":    {"parameter": "rainfall", "direction": "above",
                         "threshold": 80.0, "critical_threshold": 150.0,
                         "alert_code": "WATERLOGGING_RISK", "severity": "high"},
    "high_humidity":    {"parameter": "humidity", "direction": "above",
                         "threshold": 85.0, "critical_threshold": 95.0,
                         "alert_code": "HIGH_HUMIDITY", "severity": "medium"},
    "low_humidity":     {"parameter": "humidity", "direction": "below",
                         "threshold": 25.0, "critical_threshold": 10.0,
                         "alert_code": "LOW_HUMIDITY", "severity": "low"},
}

# =============================================================================
# SECTION 8 — ALERT DEFINITIONS
# =============================================================================
# score_impact: info 1-2 · low 3-5 · medium 5-7 · high 8-11 · critical 12-16

ALERT_DEFINITIONS: dict[str, dict[str, Any]] = {
    "LOW_N":            {"base_severity": "medium", "score_impact": 5,
                         "message": "Soil nitrogen below optimal range; crop may show yellowing and stunted growth."},
    "CRITICAL_LOW_N":   {"base_severity": "critical", "score_impact": 14,
                         "message": "Severe nitrogen deficiency detected; immediate intervention required."},
    "HIGH_N":           {"base_severity": "medium", "score_impact": 4,
                         "message": "Excess nitrogen present; risk of nitrate leaching and lodging."},
    "CRITICAL_HIGH_N":  {"base_severity": "high", "score_impact": 10,
                         "message": "Very high nitrogen; stop N fertilizer and check recent applications."},
    "LOW_P":            {"base_severity": "medium", "score_impact": 5,
                         "message": "Phosphorus deficiency; root development and flowering at risk."},
    "CRITICAL_LOW_P":   {"base_severity": "critical", "score_impact": 13,
                         "message": "Severe phosphorus deficiency; plant energy transfer compromised."},
    "HIGH_P":           {"base_severity": "low", "score_impact": 3,
                         "message": "Elevated phosphorus; may inhibit zinc and iron uptake."},
    "LOW_K":            {"base_severity": "medium", "score_impact": 5,
                         "message": "Potassium below optimal; water regulation and disease resistance reduced."},
    "CRITICAL_LOW_K":   {"base_severity": "critical", "score_impact": 13,
                         "message": "Critical potassium deficiency; fruit and grain quality severely impacted."},
    "HIGH_K":           {"base_severity": "low", "score_impact": 3,
                         "message": "Excess potassium; potential antagonism with magnesium and calcium."},
    "LOW_PH":           {"base_severity": "medium", "score_impact": 6,
                         "message": "Soil is acidic; nutrient availability and microbial activity reduced."},
    "CRITICAL_LOW_PH":  {"base_severity": "critical", "score_impact": 15,
                         "message": "Strongly acidic soil; aluminium toxicity risk; liming urgent."},
    "HIGH_PH":          {"base_severity": "medium", "score_impact": 6,
                         "message": "Alkaline soil; iron, manganese and zinc availability restricted."},
    "CRITICAL_HIGH_PH": {"base_severity": "critical", "score_impact": 14,
                         "message": "Strongly alkaline - likely sodic soil; structure and nutrient "
                                    "uptake badly affected. Test ESP / gypsum requirement."},
    "LOW_MOISTURE":     {"base_severity": "medium", "score_impact": 6,
                         "message": "Plant-available water is running low for this soil; stress is starting."},
    "CRITICAL_LOW_MOISTURE": {"base_severity": "critical", "score_impact": 16,
                         "message": "Soil is close to the wilting point; irrigate now."},
    "HIGH_MOISTURE":    {"base_severity": "medium", "score_impact": 5,
                         "message": "Soil is wetter than field capacity; roots are short of air."},
    "CRITICAL_HIGH_MOISTURE": {"base_severity": "critical", "score_impact": 15,
                         "message": "Soil is near saturation - waterlogging; root rot and nitrogen loss risk."},
    "HIGH_EC":          {"base_severity": "medium", "score_impact": 6,
                         "message": "Elevated salinity; osmotic stress limits water uptake."},
    "CRITICAL_HIGH_EC": {"base_severity": "critical", "score_impact": 16,
                         "message": "Saline soil (EC above 4 dS/m); leaching and drainage required."},
    "LOW_EC":           {"base_severity": "info", "score_impact": 2,
                         "message": "Very low EC; may indicate nutrient-poor or highly leached soil."},
    "HIGH_SOIL_TEMP":   {"base_severity": "medium", "score_impact": 3,
                         "message": "Elevated soil temperature; increased evaporation and root stress."},
    "LOW_SOIL_TEMP":    {"base_severity": "medium", "score_impact": 3,
                         "message": "Low soil temperature; slow mineralisation and root activity."},
    "HEAT_STRESS":      {"base_severity": "high", "score_impact": 4,
                         "message": "Air temperature above 38 C stresses the crop."},
    "FROST_RISK":       {"base_severity": "high", "score_impact": 4,
                         "message": "Near-freezing air temperature; frost protection advised."},
    "DROUGHT_RISK":     {"base_severity": "medium", "score_impact": 2,
                         "message": "Less than 5 mm rain in the past week; drought risk."},
    "WATERLOGGING_RISK": {"base_severity": "high", "score_impact": 3,
                         "message": "More than 80 mm rain in the past week; check drainage."},
    "HIGH_HUMIDITY":    {"base_severity": "medium", "score_impact": 2,
                         "message": "Humidity above 85 % raises fungal disease risk."},
    "LOW_HUMIDITY":     {"base_severity": "low", "score_impact": 1,
                         "message": "Humidity below 25 % speeds soil drying."},
}

# =============================================================================
# SECTION 9 — SEVERITY RULES
# =============================================================================

SEVERITY_RULES: dict[str, Any] = {
    "critical_thresholds": {
        "ph":          {"low": 4.5,  "high": 8.8},
        "nitrogen":    {"low": 8.0,  "high": 220.0},
        "phosphorus":  {"low": 3.0,  "high": 70.0},
        "potassium":   {"low": 25.0, "high": 350.0},
        "ec":          {"low": None, "high": 4.0},     # USDA: saline above 4 dS/m
        "temperature": {"low": 2.0,  "high": 45.0},
    },
    "multi_issue_overrides": {
        "min_alerts_for_override":  4,
        "score_penalty_multiplier": 1.20,
    },
    # A single parameter this extreme makes ITS alert critical.
    "extreme_value_override": {"ph_below": 4.2, "ec_above": 6.0},
    "severity_rank": {"info": 1, "low": 2, "medium": 3, "high": 4, "critical": 5},
}

# Saline-sodic signature: high EC together with pH at or above this.
SODIC_PH: float = 8.5

# =============================================================================
# SECTION 10 — FERTILIZER / AMENDMENT RECOMMENDATIONS
# =============================================================================

FERTILIZER_RECOMMENDATION_MAP: dict[str, dict[str, Any]] = {
    "LOW_N": {
        "fertilizer": "urea", "display_name": "Urea (46-0-0)", "dosage": "50–80 kg/ha",
        "timing": "Apply at early vegetative stage; split dose recommended.",
        "method": "broadcast_and_incorporate",
        "cautions": ["Incorporate within 24 h to prevent ammonia volatilisation.",
                     "Avoid surface application in hot, dry conditions."],
    },
    "CRITICAL_LOW_N": {
        "fertilizer": "ammonium_sulfate", "display_name": "Ammonium Sulphate (21-0-0-24S)",
        "dosage": "80–120 kg/ha",
        "timing": "Apply now; a 2 % foliar urea spray gives the fastest response.",
        "method": "soil_application_with_irrigation",
        "cautions": ["Acidifies soil slightly - useful on alkaline soil, avoid on acid soil.",
                     "Follow up with a second dose in 14 days."],
    },
    "HIGH_N": {
        "fertilizer": "none", "display_name": "No nitrogen fertilizer", "dosage": "0 kg/ha",
        "timing": "Withhold nitrogen until levels normalise.", "method": "withhold",
        "cautions": ["Check recent fertilizer and manure applications."],
    },
    "LOW_P": {
        "fertilizer": "dap", "display_name": "DAP — Di-Ammonium Phosphate (18-46-0)",
        "dosage": "50–100 kg/ha",
        "timing": "Basal application at sowing, placed near the root zone.",
        "method": "band_placement",
        "cautions": ["DAP adds nitrogen; reduce urea accordingly.",
                     "Less effective on highly alkaline or calcareous soil - band-place it."],
    },
    "CRITICAL_LOW_P": {
        "fertilizer": "sspa", "display_name": "Single Super Phosphate (0-16-0-11S)",
        "dosage": "250–375 kg/ha (40–60 kg P2O5)",
        "timing": "Basal application before sowing.",
        "method": "broadcast_and_incorporate",
        "cautions": ["Also supplies sulphur and calcium - valuable for oilseeds and legumes."],
    },
    "HIGH_P": {
        "fertilizer": "none", "display_name": "No phosphorus fertilizer", "dosage": "0 kg/ha",
        "timing": "Withhold phosphatic fertilizers this season.", "method": "withhold",
        "cautions": ["Excess P can lock out zinc and iron; check micronutrients."],
    },
    "LOW_K": {
        "fertilizer": "mop", "display_name": "MOP — Muriate of Potash (0-0-60)",
        "dosage": "50–80 kg/ha",
        "timing": "Apply basal or before the reproductive stage.",
        "method": "broadcast_and_irrigate",
        "cautions": ["High chloride - use sulphate of potash for chloride-sensitive crops "
                     "(potato, tobacco) or saline soil.", "Split the dose on sandy soil."],
    },
    "CRITICAL_LOW_K": {
        "fertilizer": "mop", "display_name": "MOP — Muriate of Potash (0-0-60)",
        "dosage": "100–130 kg/ha",
        "timing": "Apply now; a potassium nitrate foliar spray speeds recovery.",
        "method": "soil_plus_foliar",
        "cautions": ["MOP raises soil salinity - monitor EC after application."],
    },
    "HIGH_K": {
        "fertilizer": "none", "display_name": "No potassium fertilizer", "dosage": "0 kg/ha",
        "timing": "Withhold; check calcium and magnesium for antagonism.", "method": "withhold",
        "cautions": [],
    },
    "LOW_PH": {
        "fertilizer": "agricultural_lime", "display_name": "Agricultural Lime (CaCO3)",
        "dosage": "1.5–4.0 t/ha (by lime-requirement test)",
        "timing": "Apply 6–8 weeks before planting; incorporate to 15 cm.",
        "method": "deep_incorporation",
        "cautions": ["Over-liming locks out P, Zn and Mn.", "Re-test pH after 6 weeks."],
    },
    "CRITICAL_LOW_PH": {
        "fertilizer": "dolomitic_lime", "display_name": "Dolomitic Lime (CaMg(CO3)2)",
        "dosage": "3.0–6.0 t/ha (by lime-requirement test)",
        "timing": "Apply before the season; split doses above 4 t/ha.",
        "method": "deep_incorporation",
        "cautions": ["Supplies magnesium as well as calcium."],
    },
    # Alkaline soils: in India most are calcareous (pH 7.5-8.5, free CaCO3),
    # where acidifying the bulk soil is uneconomic. Manage the crop instead.
    "HIGH_PH": {
        "fertilizer": "acid_forming_fertilizers",
        "display_name": "Acid-forming fertilizers + organic matter + zinc",
        "dosage": "Ammonium sulphate as the N source; FYM 10 t/ha; zinc sulphate 25 kg/ha",
        "timing": "Every season, with the basal dose.",
        "method": "banded_near_roots",
        "cautions": ["Band phosphorus near roots - broadcast P is fixed as calcium phosphate.",
                     "Use chelated iron / zinc sprays if leaves yellow between veins."],
    },
    # pH above ~8.8 signals a sodic soil: reclaim with gypsum sized by a
    # gypsum-requirement test, then leach (ICAR sodic-soil practice).
    "CRITICAL_HIGH_PH": {
        "fertilizer": "gypsum", "display_name": "Gypsum (CaSO4·2H2O) - sodic soil reclamation",
        "dosage": "By gypsum-requirement test (typically 5–10 t/ha at 50 % GR)",
        "timing": "Before the season; incorporate, then pond and leach with good water.",
        "method": "broadcast_then_leach",
        "cautions": ["Confirm sodicity with an ESP / SAR test first.",
                     "Needs drainage for the displaced sodium to leave the root zone."],
    },
    "HIGH_EC": {
        "fertilizer": "none", "display_name": "Leaching irrigation - no fertilizer",
        "dosage": "Irrigation above crop need with low-salinity water (see irrigation "
                  "agent leaching requirement)",
        "timing": "Before sowing or during a low-demand period.",
        "method": "leaching_irrigation",
        "cautions": ["Hold salt-carrying fertilizers (MOP) until EC is below 2 dS/m.",
                     "Confirm with a lab ECe test - field probes read bulk EC."],
    },
    # Saline but NOT sodic: gypsum adds salt and does not help. Leach and drain.
    "CRITICAL_HIGH_EC": {
        "fertilizer": "none", "display_name": "Reclamation leaching + drainage",
        "dosage": "Ponded leaching with good water; subsurface drainage where the water table is high",
        "timing": "Before the next season.",
        "method": "reclamation_leaching",
        "cautions": ["Do not add gypsum to a saline, non-sodic soil - it raises salinity.",
                     "Grow a salt-tolerant crop (barley, cotton, guar) meanwhile."],
    },
    # Saline AND sodic (high EC with pH >= 8.5): gypsum, then leach.
    "CRITICAL_HIGH_EC_SODIC": {
        "fertilizer": "gypsum", "display_name": "Gypsum + leaching (saline-sodic soil)",
        "dosage": "By gypsum-requirement test, then ponded leaching",
        "timing": "Before the next season.",
        "method": "broadcast_then_leach",
        "cautions": ["Confirm with ESP / SAR and ECe tests.", "Drainage is essential."],
    },
}

# 7-in-1 soil probes have no nutrient electrodes: their N, P and K are
# calculated from the conductivity signal. Deficiency alerts from them are
# advisory, and no fertilizer is dosed on them - dosing on an EC-derived
# number would fertilize salinity, not the crop.
SENSOR_NUTRIENT_PARAMETERS = ("nitrogen", "phosphorus", "potassium")
SENSOR_NUTRIENT_SEVERITY_CAP = "low"
SENSOR_NUTRIENT_IMPACT_FACTOR = 0.5
SENSOR_NUTRIENT_SUFFIX = " (sensor estimate - confirm with a soil test before fertilizing)"
SOIL_TEST_FIRST_RECOMMENDATION: dict[str, Any] = {
    "fertilizer": "soil_test_first",
    "display_name": "Lab soil test before any N/P/K fertilizer",
    "dosage": "No dose from sensor NPK",
    "timing": "Before the next fertilizer application.",
    "method": "Soil Health Card test at the nearest soil-testing laboratory",
    "cautions": ["In-field 7-in-1 sensors estimate N, P and K from conductivity; they follow "
                 "salts and moisture, not the nutrients.",
                 "Send lab values with nutrient_source='lab' for fertilizer doses."],
}

# Low nitrogen on a legume: feed the nodules, not the soil.
LEGUME_LOW_N_RECOMMENDATION: dict[str, Any] = {
    "fertilizer": "rhizobium_plus_starter_n",
    "display_name": "Rhizobium seed inoculation + starter nitrogen",
    "dosage": "Rhizobium 600 g per ha-seed lot; starter 20 kg N/ha (~43 kg urea)",
    "timing": "Inoculate seed just before sowing; starter N basal.",
    "method": "seed_treatment_plus_basal",
    "cautions": ["A full urea programme suppresses nodulation - legumes fix most of "
                 "their own nitrogen.", "Nodulation needs pH 6.0-7.5 and adequate "
                 "phosphorus and molybdenum."],
}

# =============================================================================
# SECTION 11 — SUGGESTIONS
# =============================================================================

SINGLE_ALERT_SUGGESTIONS: dict[str, list[str]] = {
    "LOW_N":                  ["Apply split-dose nitrogen fertilizer.",
                               "Test for sulphur deficiency - often co-occurs with N deficiency."],
    "CRITICAL_LOW_N":         ["Apply nitrogen now; a 2 % foliar urea spray acts fastest."],
    "HIGH_N":                 ["Stop nitrogen applications.", "Check recent fertilizer history."],
    "LOW_P":                  ["Band-place phosphate near the roots.",
                               "Check soil pH - P availability drops below 5.5 and above 7.5."],
    "CRITICAL_LOW_P":         ["Apply phosphate basal before sowing."],
    "HIGH_P":                 ["Test zinc and iron.", "Withhold phosphatic fertilizers this season."],
    "LOW_K":                  ["Apply potassium before the reproductive stage."],
    "CRITICAL_LOW_K":         ["Apply potash now; a foliar potassium spray speeds recovery."],
    "HIGH_K":                 ["Test calcium and magnesium.", "Withhold potassic fertilizers."],
    "LOW_PH":                 ["Apply agricultural lime and incorporate to root depth.",
                               "Test exchangeable aluminium if pH is below 5.0."],
    "CRITICAL_LOW_PH":        ["Lime before sowing; delay planting until pH recovers.",
                               "Test for aluminium toxicity."],
    "HIGH_PH":                ["Use ammonium sulphate as the nitrogen source.",
                               "Add organic matter; band phosphorus; supply zinc."],
    "CRITICAL_HIGH_PH":       ["Test ESP / gypsum requirement - this is likely a sodic soil.",
                               "Consult the local soil-testing laboratory for a reclamation plan."],
    "LOW_MOISTURE":           ["Irrigate - plant-available water is running low.",
                               "Mulch to conserve soil moisture."],
    "CRITICAL_LOW_MOISTURE":  ["Irrigate now - the crop is close to wilting.",
                               "Check the drip / sprinkler system for failures."],
    "HIGH_MOISTURE":          ["Delay irrigation.", "Improve field drainage."],
    "CRITICAL_HIGH_MOISTURE": ["Open or clear drainage channels.",
                               "Keep machinery off the field until it drains."],
    "HIGH_EC":                ["Leach with low-salinity water.",
                               "Hold salt-carrying fertilizers until EC is below 2 dS/m."],
    "CRITICAL_HIGH_EC":       ["Plan reclamation leaching with drainage.",
                               "Grow a salt-tolerant crop in the meantime."],
    "LOW_EC":                 ["Soil may be nutrient-poor; get a full soil test."],
    "HEAT_STRESS":            ["Irrigate more often, in the evening or early morning.",
                               "Mulch to keep the root zone cool."],
    "FROST_RISK":             ["Irrigate lightly the evening before a frost night.",
                               "Cover nurseries and sensitive crops."],
    "DROUGHT_RISK":           ["Keep supplemental irrigation ready."],
    "WATERLOGGING_RISK":      ["Open drainage furrows.", "Delay irrigation."],
    "HIGH_HUMIDITY":          ["Improve canopy airflow.", "Scout for fungal lesions."],
    "LOW_HUMIDITY":           ["Mulch to slow evaporation."],
}

MULTI_CONDITION_SUGGESTIONS: list[dict[str, Any]] = [
    {"conditions": ["LOW_N", "LOW_PH"], "priority": "high",
     "suggestion": "Correct acidity first - liming improves nitrogen availability before "
                   "adding N fertilizer."},
    {"conditions": ["HIGH_EC", "HIGH_N"], "priority": "critical",
     "suggestion": "Salinity and excess nitrogen together: leach before any fertilizer."},
    {"conditions": ["LOW_MOISTURE", "HIGH_EC"], "priority": "high",
     "suggestion": "Dry soil concentrates salts. Irrigate slowly to rehydrate and leach together."},
    {"conditions": ["HIGH_MOISTURE", "LOW_N"], "priority": "high",
     "suggestion": "Waterlogging drives nitrogen loss by denitrification. Drain before N; "
                   "use neem-coated urea."},
    {"conditions": ["LOW_P", "HIGH_PH"], "priority": "medium",
     "suggestion": "High pH fixes phosphorus as calcium phosphate - band-place P near the "
                   "roots and add organic matter."},
    {"conditions": ["LOW_K", "HIGH_EC"], "priority": "high",
     "suggestion": "Muriate of potash adds chloride and raises EC - use sulphate of potash."},
    {"conditions": ["HEAT_STRESS", "LOW_MOISTURE"], "priority": "critical",
     "suggestion": "Heat and dry soil together: irrigate at night by drip to cut evaporation."},
    {"conditions": ["HIGH_HUMIDITY", "HIGH_MOISTURE"], "priority": "high",
     "suggestion": "Disease-conducive conditions: reduce irrigation, improve drainage, and "
                   "scout for fungal disease."},
    {"conditions": ["LOW_N", "LOW_P", "LOW_K"], "priority": "critical",
     "suggestion": "All three major nutrients are low: apply a balanced NPK complex "
                   "(e.g. 10-26-26 basal) and top-dress nitrogen."},
    {"conditions": ["CRITICAL_LOW_N", "DROUGHT_RISK"], "priority": "critical",
     "suggestion": "Nitrogen deficiency in dry soil: a 2 % foliar urea spray works better "
                   "than soil application."},
]

# =============================================================================
# SECTION 12 — CONFLICT DETECTION (fertilizer applied vs soil condition)
# =============================================================================

CONFLICT_DETECTION_MAP: dict[str, dict[str, Any]] = {
    "urea": {"expected_fix": ["LOW_N"], "expected_window": 14,
             "conflict_if_present": ["HIGH_PH", "WATERLOGGING_RISK"],
             "conflict_reason": "Urea loses nitrogen as ammonia on alkaline soil and by "
                                "denitrification when waterlogged.",
             "alternative": "ammonium_sulfate"},
    "dap": {"expected_fix": ["LOW_P", "LOW_N"], "expected_window": 21,
            "conflict_if_present": ["CRITICAL_HIGH_PH"],
            "conflict_reason": "Phosphate is fixed as calcium phosphate on strongly alkaline soil.",
            "alternative": "sspa"},
    "mop": {"expected_fix": ["LOW_K"], "expected_window": 14,
            "conflict_if_present": ["HIGH_EC", "CRITICAL_HIGH_EC"],
            "conflict_reason": "Muriate of potash contains chloride, which raises EC.",
            "alternative": "potassium_sulfate"},
    "sspa": {"expected_fix": ["LOW_P"], "expected_window": 21,
             "conflict_if_present": ["LOW_PH"],
             "conflict_reason": "SSP's sulphur can further acidify an already acidic soil.",
             "alternative": "rock_phosphate_with_lime"},
    "ammonium_sulfate": {"expected_fix": ["LOW_N"], "expected_window": 10,
                         "conflict_if_present": ["LOW_PH", "CRITICAL_LOW_PH"],
                         "conflict_reason": "Ammonium sulphate acidifies soil; it worsens low pH.",
                         "alternative": "calcium_ammonium_nitrate"},
    "agricultural_lime": {"expected_fix": ["LOW_PH", "CRITICAL_LOW_PH"], "expected_window": 42,
                          "conflict_if_present": ["HIGH_PH", "CRITICAL_HIGH_PH"],
                          "conflict_reason": "Lime on an alkaline soil raises pH further.",
                          "alternative": "acid_forming_fertilizers"},
    "elemental_sulfur": {"expected_fix": ["HIGH_PH"], "expected_window": 56,
                         "conflict_if_present": ["LOW_PH", "CRITICAL_LOW_PH"],
                         "conflict_reason": "Further acidification would breach the pH floor.",
                         "alternative": "none"},
    "gypsum": {"expected_fix": ["CRITICAL_HIGH_PH"], "expected_window": 90,
               "conflict_if_present": [],
               "conflict_reason": "",
               "alternative": "none"},
    "organic_compost": {"expected_fix": ["LOW_N", "LOW_P", "LOW_K", "LOW_EC"], "expected_window": 30,
                        "conflict_if_present": ["CRITICAL_HIGH_EC"],
                        "conflict_reason": "Compost salts can raise EC further in saline soil.",
                        "alternative": "vermicompost_low_salt"},
    "npk_complex": {"expected_fix": ["LOW_N", "LOW_P", "LOW_K"], "expected_window": 14,
                    "conflict_if_present": ["HIGH_EC", "HIGH_N"],
                    "conflict_reason": "A complex fertilizer worsens existing salinity or N excess.",
                    "alternative": "targeted_single_nutrient_application"},
}

FERTILIZER_ALIASES: dict[str, str] = {
    "urea": "urea", "neem coated urea": "urea",
    "dap": "dap", "di-ammonium phosphate": "dap", "diammonium phosphate": "dap",
    "mop": "mop", "muriate of potash": "mop",
    "npk": "npk_complex", "npk complex": "npk_complex", "npk_complex": "npk_complex",
    "ssp": "sspa", "sspa": "sspa", "single super phosphate": "sspa",
    "ammonium sulfate": "ammonium_sulfate", "ammonium sulphate": "ammonium_sulfate",
    "lime": "agricultural_lime", "agricultural lime": "agricultural_lime",
    "sulphur": "elemental_sulfur", "sulfur": "elemental_sulfur",
    "gypsum": "gypsum",
    "compost": "organic_compost", "organic compost": "organic_compost",
    "organic_compost": "organic_compost", "fym": "organic_compost",
    "none": "none",
}

# =============================================================================
# SECTION 13 — SCORING
# =============================================================================

SCORE_WEIGHTS: dict[str, float] = {
    "moisture": 0.20, "ph": 0.15, "nitrogen": 0.18, "phosphorus": 0.12,
    "potassium": 0.12, "ec": 0.10, "temperature": 0.08, "humidity": 0.05,
}

CROP_SCORE_WEIGHT_OVERRIDES: dict[str, dict[str, float]] = {
    "rice":      {"moisture": 0.28, "ph": 0.16, "nitrogen": 0.16, "potassium": 0.13, "ec": 0.07},
    "cotton":    {"potassium": 0.20, "moisture": 0.18, "ph": 0.14, "nitrogen": 0.15, "ec": 0.08},
    "sugarcane": {"nitrogen": 0.20, "potassium": 0.18, "moisture": 0.22, "ph": 0.12, "ec": 0.08},
    "potato":    {"potassium": 0.20, "ph": 0.18, "moisture": 0.20, "temperature": 0.12,
                  "nitrogen": 0.15},
    "soybean":   {"ph": 0.18, "phosphorus": 0.16, "moisture": 0.18, "nitrogen": 0.08},
    "groundnut": {"ph": 0.16, "phosphorus": 0.16, "moisture": 0.20, "nitrogen": 0.08,
                  "ec": 0.12},
    "guar":      {"phosphorus": 0.18, "moisture": 0.16, "nitrogen": 0.06},
    "white peas": {"ph": 0.16, "phosphorus": 0.16, "nitrogen": 0.08},
    "tomato":    {"potassium": 0.16, "moisture": 0.22, "ec": 0.12},
}

SCORE_BANDS: dict[str, dict[str, Any]] = {
    "excellent": {"min": 85, "max": 100, "label": "Excellent"},
    "good":      {"min": 70, "max": 84,  "label": "Good"},
    "fair":      {"min": 50, "max": 69,  "label": "Fair"},
    "poor":      {"min": 30, "max": 49,  "label": "Poor"},
    "critical":  {"min": 0,  "max": 29,  "label": "Critical"},
}

# =============================================================================
# SECTION 14 — SUMMARY TEXT
# =============================================================================

SUMMARY_FRAGMENTS: dict[str, str] = {
    "LOW_N": "nitrogen deficiency detected",
    "CRITICAL_LOW_N": "critical nitrogen shortage",
    "HIGH_N": "excess nitrogen present",
    "CRITICAL_HIGH_N": "very high nitrogen",
    "LOW_P": "phosphorus below optimal levels",
    "CRITICAL_LOW_P": "severe phosphorus deficiency",
    "HIGH_P": "phosphorus accumulation noted",
    "LOW_K": "potassium shortage detected",
    "CRITICAL_LOW_K": "critical potassium deficiency",
    "HIGH_K": "excess potassium in soil",
    "LOW_PH": "acidic soil",
    "CRITICAL_LOW_PH": "strongly acidic soil",
    "HIGH_PH": "alkaline soil",
    "CRITICAL_HIGH_PH": "strongly alkaline, likely sodic soil",
    "LOW_MOISTURE": "plant-available water running low",
    "CRITICAL_LOW_MOISTURE": "soil close to wilting point",
    "HIGH_MOISTURE": "soil wetter than field capacity",
    "CRITICAL_HIGH_MOISTURE": "waterlogged soil",
    "HIGH_EC": "elevated soil salinity",
    "CRITICAL_HIGH_EC": "saline soil",
    "LOW_EC": "very low soil ionic activity",
    "HIGH_SOIL_TEMP": "high soil temperature",
    "LOW_SOIL_TEMP": "low soil temperature",
    "HEAT_STRESS": "air heat stress",
    "FROST_RISK": "frost risk",
    "DROUGHT_RISK": "little recent rain",
    "WATERLOGGING_RISK": "heavy recent rain",
    "HIGH_HUMIDITY": "high humidity - fungal risk",
    "LOW_HUMIDITY": "low humidity",
}

SUMMARY_TEMPLATES: dict[str, str] = {
    "no_alerts":    "Soil health is {score_label}. All parameters are within optimal range for {crop_type}.",
    "single_alert": "Soil health is {score_label} (score: {score}/100). Issue detected: {alert_fragment}. Recommendation: {recommendation}.",
    "multi_alert":  "Soil health score is {score}/100 ({score_label}). {alert_count} issues detected: {alert_list}. Priority action: {top_recommendation}.",
    "critical":     "CRITICAL soil health status (score: {score}/100). Immediate action required. Primary concern: {primary_alert}.",
}

# =============================================================================
# SECTION 15 — DATA QUALITY
# =============================================================================
# Deducted when an input that CHANGES the analysis is missing. Inputs the
# analysis does not use (season, growth_stage, region, field_id) cost nothing.

DATA_QUALITY_WEIGHTS: dict[str, float] = {
    "soil_moisture":    0.12,
    "nitrogen":         0.06,
    "phosphorus":       0.05,
    "potassium":        0.05,
    "soil_temperature": 0.03,
    "air_temperature":  0.02,
    "air_humidity":     0.02,
    "crop_type":        0.15,   # sets optimal ranges, salt tolerance, legume advice
    "soil_type":        0.15,   # sets how moisture is read
    "rainfall":         0.04,
    "fertilizer_type":  0.04,   # enables conflict detection
}
