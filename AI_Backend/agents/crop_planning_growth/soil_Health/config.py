# =============================================================================
# config.py — Soil Health Agent Configuration
# Multi-Agent Farming System | FastAPI Backend
# =============================================================================
# Maintainer  : Soil Health Agent Team
# Version     : 2.1.0
# Last Updated: 2025
# Description : Production-level, domain-accurate, fully configurable settings
#               for a context-aware Soil Health Agent operating inside a
#               multi-agent agricultural intelligence system.
#
# CALIBRATION HISTORY:
#   v1.0.0 — Initial release (used fertilizer-dose values as soil-test ranges)
#   v2.0.0 — Fixed nutrient ranges to ICAR soil-test norms (mineral-N, Olsen-P,
#             NH4OAc-K); rebalanced alert score penalties
#   v2.1.0 — Targeted calibration for Indian field conditions:
#             K min 80→60, temp max 30→35, EC max 1.5→1.8, multi-issue
#             override threshold 3→4 alerts, SCORE_FLOOR=15, INFO suppression
#
# SCIENTIFIC BASIS:
#   Nitrogen  : Mineral available-N (NO3-N + NH4-N) as read by IoT soil sensors
#               ICAR Subbiah-Asija method converted to sensor-readable mg/kg
#   Phosphorus: Olsen-P (NaHCO3 extract) — ICAR standard (Low <10, Med 10-25)
#   Potassium : NH4OAc-extractable K — ICAR (Low <55, Med 55-140, High >140 mg/kg)
#   EC        : Saturated paste extract; USDA non-saline class 0-2 dS/m
#   Temperature: Root-zone at 10-15 cm sensor depth, Indian Kharif/Rabi calibrated
# =============================================================================

from __future__ import annotations
from typing import Any

# =============================================================================
# SECTION 1 — AGENT IDENTITY & METADATA
# =============================================================================

AGENT_ID      = "soil_health_agent"
AGENT_VERSION = "2.1.0"
AGENT_NAME    = "Soil Health Monitor"
AGENT_ROLE    = "soil_analysis"

AGENT_METADATA: dict[str, Any] = {
    "description": "Monitors and evaluates soil health using multi-sensor input, "
                   "crop-context, soil-type modifiers, and seasonal rules.",
    "input_modalities":  ["sensor", "context", "weather"],
    "output_types":      ["alerts", "recommendations", "score", "summary"],
    "supports_streaming": True,
    "ml_ready":           True,
}

# =============================================================================
# SECTION 2 — INPUT PARAMETER REGISTRY
# =============================================================================

SOIL_PARAMETERS = [
    "moisture",         # % volumetric water content
    "temperature",      # °C at 10–15 cm sensor depth
    "ph",               # dimensionless (0–14)
    "nitrogen",         # mg/kg — mineral-N (NO3-N + NH4-N), IoT sensor value
    "phosphorus",       # mg/kg — Olsen-P equivalent
    "potassium",        # mg/kg — NH4OAc-extractable K
    "ec",               # dS/m — electrical conductivity (saturated paste)
]

AIR_PARAMETERS = [
    "air_temperature",  # °C ambient
    "humidity",         # % relative humidity
]

CONTEXT_PARAMETERS = [
    "soil_type",
    "crop_type",
    "rainfall",         # mm over last 7 days
    "irrigation_amount",       # mm applied last 7 days
    "fertilizer_type",       # last fertilizer applied (string key)
    "growth_stage",     # optional: seedling | vegetative | flowering | harvest
    "season",           # optional: summer | winter | monsoon
    "region",           # optional: free-text or code
    "field_id",         # optional: unique field identifier
]

# =============================================================================
# SECTION 3 — VALIDATION LAYER (Real-World Agriculture Standards)
# =============================================================================

VALID_RANGES: dict[str, dict[str, float]] = {
    # Soil sensor parameters
    "moisture":        {"min": 0.0,   "max": 100.0},
    "temperature":     {"min": -10.0, "max": 60.0},
    "ph":              {"min": 3.0,   "max": 10.0},
    "nitrogen":        {"min": 0.0,   "max": 500.0},   # mineral-N sensor range
    "phosphorus":      {"min": 0.0,   "max": 200.0},   # Olsen-P sensor range
    "potassium":       {"min": 0.0,   "max": 800.0},   # NH4OAc-K sensor range
    "ec":              {"min": 0.0,   "max": 16.0},
    # Air parameters
    "air_temperature": {"min": -20.0, "max": 55.0},
    "humidity":        {"min": 0.0,   "max": 100.0},
    # Contextual numeric inputs
    "rainfall":        {"min": 0.0,   "max": 500.0},
    "irrigation":      {"min": 0.0,   "max": 200.0},
}

VALID_CATEGORICAL: dict[str, list[str]] = {
    "soil_type":    ["sandy", "clay", "loamy", "peaty", "silt"],
    "crop_type":    ["wheat", "rice", "maize", "cotton", "sugarcane",
                     "soybean", "sunflower", "barley", "tomato", "potato"],
    "season":       ["summer", "winter", "monsoon"],
    "growth_stage": ["seedling", "vegetative", "flowering", "maturity", "harvest"],
    "fertilizer":   ["urea", "dap", "mop", "npk_complex", "sspa",
                     "ammonium_sulfate", "organic_compost", "none"],
}

# =============================================================================
# SECTION 4 — GLOBAL OPTIMAL RANGES
# =============================================================================
# All ranges are real soil-test values read by IoT sensors.
#
# Nitrogen  (30–90 mg/kg):  Mineral-N window for active crop uptake.
#                            Values below 30 = approaching deficiency;
#                            above 90 = excess / leaching risk.
# Phosphorus (10–28 mg/kg): Olsen-P medium class (ICAR). Low <10, High >28.
# Potassium  (60–160 mg/kg): NH4OAc-K. Min 60 covers productive red/laterite
#                             soils of South India (ICAR medium starts ~55).
# EC         (0.2–1.8 dS/m): USDA non-saline class ceiling is 2.0 dS/m.
#                             Irrigated Indo-Gangetic background is 0.5–1.8.
# Temperature (12–35 °C):   Root-zone at 10–15 cm. Kharif season regularly
#                             28–35 °C; Rabi down to 12 °C. Max 35 avoids
#                             false HIGH_SOIL_TEMP all summer.
# =============================================================================

GLOBAL_OPTIMAL_RANGES: dict[str, dict[str, float]] = {
    "moisture":        {"min": 40.0,  "max": 70.0},
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
# ALERT THRESHOLDS (Risk Detection)
# =============================================================================
# Separate from GLOBAL_OPTIMAL_RANGES/CROP_CONFIG optimal ranges (used for scoring).
# Alerts should represent agronomic risk, not minor deviation from "best".
# Keys match config parameter names (moisture, temperature, ph, nitrogen, ...).

ALERT_THRESHOLDS: dict[str, dict[str, float]] = {
    # Root-zone soil temperature: Indian fields often sit at 28–35 °C in summer;
    # treat >35 °C as heat-risk, not merely "above optimal" for cool crops.
    "temperature": {"high": 35.0},

    # EC (dS/m): keep farmer alerts above 2.0 (borderline saline). Critical handled
    # separately via SEVERITY_RULES["critical_thresholds"]["ec"]["high"] (4.0).
    "ec":          {"high": 2.0},

    # pH: below 5.5 or above 8.5 meaningfully impacts nutrient availability in Indian soils.
    "ph":          {"low": 5.5, "high": 8.5},

    # Moisture: below 30% indicates likely stress for most crops; extreme handled via critical_thresholds.
    "moisture":    {"low": 30.0, "high": 85.0},

    # Nutrients: alerts represent deficiency/excess risk, not mild below-optimal.
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
# SECTION 5 — CROP-SPECIFIC CONFIGURATION
# =============================================================================
# optimal_ranges : calibrated soil-test sensor thresholds per crop
# nutrient_needs : relative priority — low | medium | high | critical
# growth_sensitive: parameters where deviation causes rapid yield loss
# water_stress_threshold: moisture % below which stress begins
# salinity_tolerance: qualitative USDA classification
# max_ec: crop-specific EC½ threshold (dS/m) — yield halved above this
# notes: agronomic reference
#
# NUTRIENT RANGE BASIS (all crops):
#   N  — mineral-N (NO3+NH4) IoT sensor; not Subbiah-Asija bulk kg/ha
#   P  — Olsen-P; ICAR Low<10, Medium 10-25, High >25 mg/kg
#   K  — NH4OAc-K; ICAR Low<55, Medium 55-140, High >140 mg/kg
# =============================================================================

CROP_CONFIG: dict[str, dict[str, Any]] = {

    # ─────────────────────────────────────────────────────────────────────────
    "wheat": {
        "display_name": "Wheat (Triticum aestivum)",
        "optimal_ranges": {
            # Rabi cool-season crop; moderate N, P demand; tolerates moderate salinity
            "moisture":    {"min": 40.0,  "max": 65.0},
            "temperature": {"min": 10.0,  "max": 25.0},   # cool-season; stress >28 °C
            "ph":          {"min": 6.0,   "max": 7.5},
            "nitrogen":    {"min": 30.0,  "max": 90.0},   # mg/kg mineral-N
            "phosphorus":  {"min": 10.0,  "max": 25.0},   # mg/kg Olsen-P
            "potassium":   {"min": 60.0,  "max": 150.0},  # mg/kg NH4OAc-K
            "ec":          {"min": 0.2,   "max": 2.2},    # EC½ = 6.0 dS/m; tolerant
        },
        "nutrient_needs": {
            "nitrogen":   "critical",
            "phosphorus": "high",
            "potassium":  "medium",
        },
        "growth_sensitive":        ["temperature", "moisture", "nitrogen"],
        "water_stress_threshold":  38.0,
        "salinity_tolerance":      "moderate",
        "max_ec":                  6.0,
        "notes": "Nitrogen critical at tillering and grain fill. Split N application recommended.",
    },

    # ─────────────────────────────────────────────────────────────────────────
    "rice": {
        "display_name": "Rice (Oryza sativa)",
        "optimal_ranges": {
            # Flooded/paddy conditions; high moisture; anaerobic N cycling lowers N range
            "moisture":    {"min": 65.0,  "max": 90.0},   # flooded / near-saturated
            "temperature": {"min": 22.0,  "max": 35.0},
            "ph":          {"min": 5.5,   "max": 7.0},
            "nitrogen":    {"min": 25.0,  "max": 80.0},   # lower — anaerobic denitrification
            "phosphorus":  {"min": 8.0,   "max": 22.0},
            "potassium":   {"min": 55.0,  "max": 140.0},  # paddy K uptake lower than upland
            "ec":          {"min": 0.1,   "max": 1.5},    # sensitive; EC½ = 3.0 dS/m
        },
        "nutrient_needs": {
            "nitrogen":   "critical",
            "phosphorus": "medium",
            "potassium":  "high",
        },
        "growth_sensitive":        ["moisture", "temperature", "ph"],
        "water_stress_threshold":  60.0,
        "salinity_tolerance":      "sensitive",
        "max_ec":                  3.0,
        "notes": "Flooded conditions preferred. Sensitive to salinity. "
                 "Anaerobic N cycling reduces mineral-N availability.",
    },

    # ─────────────────────────────────────────────────────────────────────────
    "maize": {
        "display_name": "Maize / Corn (Zea mays)",
        "optimal_ranges": {
            # Kharif crop; grows 26–36 °C across India; higher EC tolerance
            "moisture":    {"min": 45.0,  "max": 70.0},
            "temperature": {"min": 18.0,  "max": 35.0},   # Kharif root-zone reality
            "ph":          {"min": 5.8,   "max": 7.0},
            "nitrogen":    {"min": 35.0,  "max": 90.0},
            "phosphorus":  {"min": 12.0,  "max": 28.0},
            "potassium":   {"min": 65.0,  "max": 160.0},
            "ec":          {"min": 0.2,   "max": 2.0},    # EC½ = 5.9 dS/m; moderately tolerant
        },
        "nutrient_needs": {
            "nitrogen":   "critical",
            "phosphorus": "high",
            "potassium":  "high",
        },
        "growth_sensitive":        ["nitrogen", "moisture", "temperature"],
        "water_stress_threshold":  42.0,
        "salinity_tolerance":      "moderate",
        "max_ec":                  5.9,
        "notes": "High N demand especially at V6–VT stages. "
                 "Kharif maize tolerates root-zone temps up to 35 °C.",
    },

    # ─────────────────────────────────────────────────────────────────────────
    "cotton": {
        "display_name": "Cotton (Gossypium hirsutum)",
        "optimal_ranges": {
            # Deep-rooted; high K for boll/fibre quality; broad pH tolerance
            "moisture":    {"min": 40.0,  "max": 65.0},
            "temperature": {"min": 22.0,  "max": 38.0},
            "ph":          {"min": 6.0,   "max": 8.0},
            "nitrogen":    {"min": 25.0,  "max": 80.0},   # excess N → vegetative excess
            "phosphorus":  {"min": 8.0,   "max": 22.0},
            "potassium":   {"min": 90.0,  "max": 190.0},  # high K demand; boll fill
            "ec":          {"min": 0.2,   "max": 2.5},    # EC½ = 7.7 dS/m; tolerant
        },
        "nutrient_needs": {
            "nitrogen":   "high",
            "phosphorus": "medium",
            "potassium":  "critical",
        },
        "growth_sensitive":        ["potassium", "temperature", "ph"],
        "water_stress_threshold":  32.0,
        "salinity_tolerance":      "moderate",
        "max_ec":                  7.7,
        "notes": "Potassium critical for boll development and fibre quality. "
                 "Excess N causes excessive vegetative growth at cost of yield.",
    },

    # ─────────────────────────────────────────────────────────────────────────
    "sugarcane": {
        "display_name": "Sugarcane (Saccharum officinarum)",
        "optimal_ranges": {
            # Long-duration; heavy N and K feeder; split fertilizer applications essential
            "moisture":    {"min": 55.0,  "max": 80.0},
            "temperature": {"min": 25.0,  "max": 38.0},
            "ph":          {"min": 6.0,   "max": 7.5},
            "nitrogen":    {"min": 40.0,  "max": 100.0},
            "phosphorus":  {"min": 10.0,  "max": 25.0},
            "potassium":   {"min": 90.0,  "max": 190.0},
            "ec":          {"min": 0.2,   "max": 2.0},    # EC½ = 1.7 dS/m; sensitive
        },
        "nutrient_needs": {
            "nitrogen":   "critical",
            "phosphorus": "medium",
            "potassium":  "critical",
        },
        "growth_sensitive":        ["moisture", "nitrogen", "potassium"],
        "water_stress_threshold":  50.0,
        "salinity_tolerance":      "sensitive",
        "max_ec":                  1.7,
        "notes": "Long growing season (12–18 months). "
                 "Split N and K applications strongly advised.",
    },

    # ─────────────────────────────────────────────────────────────────────────
    "soybean": {
        "display_name": "Soybean (Glycine max)",
        "optimal_ranges": {
            # N-fixing legume; lower soil N needed; pH-sensitive rhizobia activity
            "moisture":    {"min": 40.0,  "max": 65.0},
            "temperature": {"min": 18.0,  "max": 32.0},   # comfortable in Kharif heat
            "ph":          {"min": 6.0,   "max": 7.0},    # rhizobia active 6.0–7.0
            "nitrogen":    {"min": 15.0,  "max": 60.0},   # low — biological N-fixation
            "phosphorus":  {"min": 10.0,  "max": 28.0},
            "potassium":   {"min": 60.0,  "max": 150.0},
            "ec":          {"min": 0.1,   "max": 1.5},    # EC½ = 5.0 dS/m but keep safe
        },
        "nutrient_needs": {
            "nitrogen":   "medium",    # rhizobia fixation reduces external N need
            "phosphorus": "high",
            "potassium":  "high",
        },
        "growth_sensitive":        ["ph", "phosphorus", "moisture"],
        "water_stress_threshold":  38.0,
        "salinity_tolerance":      "sensitive",
        "max_ec":                  5.0,
        "notes": "Biological N-fixation via Bradyrhizobium reduces soil N requirement. "
                 "pH must stay 6.0–7.0 for effective nodulation.",
    },

    # ─────────────────────────────────────────────────────────────────────────
    "potato": {
        "display_name": "Potato (Solanum tuberosum)",
        "optimal_ranges": {
            # Cool-season Rabi crop; high K for tuber starch; low-pH tolerant
            "moisture":    {"min": 55.0,  "max": 75.0},
            "temperature": {"min": 10.0,  "max": 20.0},   # tuber initiation fails >25 °C
            "ph":          {"min": 5.0,   "max": 6.5},    # scab disease risk above 6.5
            "nitrogen":    {"min": 28.0,  "max": 85.0},
            "phosphorus":  {"min": 12.0,  "max": 30.0},
            "potassium":   {"min": 90.0,  "max": 195.0},  # high K for tuber bulking
            "ec":          {"min": 0.1,   "max": 1.5},    # EC½ = 1.7 dS/m; sensitive
        },
        "nutrient_needs": {
            "nitrogen":   "high",
            "phosphorus": "high",
            "potassium":  "critical",
        },
        "growth_sensitive":        ["temperature", "moisture", "potassium"],
        "water_stress_threshold":  48.0,
        "salinity_tolerance":      "sensitive",
        "max_ec":                  1.7,
        "notes": "Cool soil (10–20 °C) critical for tuber initiation. "
                 "Keep pH 5.0–6.5 to avoid common scab (Streptomyces).",
    },
}

# =============================================================================
# SECTION 6 — SOIL TYPE CONFIGURATION
# =============================================================================
# score_modifiers: multipliers applied during health scoring.
# Values > 1.0 amplify the parameter weight; < 1.0 reduce it.
# ─────────────────────────────────────────────────────────────────────────────
# Indian soil context:
#   Sandy  : Rajasthan, Gujarat coastal — low CEC, rapid K/N leaching
#   Clay   : Vertisols (Maharashtra, MP) — waterlogging risk, high K naturally
#   Loamy  : Indo-Gangetic alluvial — ideal balanced properties
#   Peaty  : Limited occurrence (Kerala backwaters, NE India) — highly acidic
#   Silt   : Gangetic delta, river floodplains — crusting risk
# =============================================================================

SOIL_TYPE_CONFIG: dict[str, dict[str, Any]] = {

    "sandy": {
        "display_name":        "Sandy Soil",
        "water_retention":     0.30,
        "nutrient_retention":  0.25,
        "drainage":            0.90,
        "aeration":            0.95,
        "compaction_risk":     0.10,
        "typical_ph_range":    {"min": 5.0, "max": 7.0},
        "score_modifiers": {
            "moisture":    1.25,   # dries quickly; deviations penalised more
            "nitrogen":    1.20,   # leaches rapidly — sandy CEC very low
            "phosphorus":  1.10,
            "ec":          0.90,   # salts flush through; EC less concerning
        },
        "irrigation_frequency_multiplier": 1.5,
        "fertilizer_frequency_multiplier": 1.4,
        "notes": "Low CEC; prone to drought and nutrient leaching. "
                 "Split fertilizer applications essential.",
    },

    "clay": {
        "display_name":        "Clay Soil",
        "water_retention":     0.85,
        "nutrient_retention":  0.80,
        "drainage":            0.20,
        "aeration":            0.30,
        "compaction_risk":     0.85,
        "typical_ph_range":    {"min": 6.0, "max": 8.0},
        "score_modifiers": {
            "moisture":    1.30,   # waterlogging risk is primary concern
            "ec":          1.20,   # salt accumulation without drainage
            "nitrogen":    0.90,
            "ph":          1.15,
        },
        "irrigation_frequency_multiplier": 0.7,
        "fertilizer_frequency_multiplier": 0.8,
        "notes": "High CEC; risk of waterlogging and compaction. "
                 "Black cotton soils naturally high in K (200–450 mg/kg).",
    },

    "loamy": {
        "display_name":        "Loamy Soil",
        "water_retention":     0.65,
        "nutrient_retention":  0.70,
        "drainage":            0.60,
        "aeration":            0.70,
        "compaction_risk":     0.30,
        "typical_ph_range":    {"min": 6.0, "max": 7.5},
        "score_modifiers": {
            "moisture":    1.00,
            "nitrogen":    1.00,
            "phosphorus":  1.00,
            "potassium":   1.00,
            "ec":          1.00,
        },
        "irrigation_frequency_multiplier": 1.0,
        "fertilizer_frequency_multiplier": 1.0,
        "notes": "Ideal agricultural soil; balanced water and nutrient retention. "
                 "Reference soil for baseline scoring.",
    },

    "peaty": {
        "display_name":        "Peaty Soil",
        "water_retention":     0.90,
        "nutrient_retention":  0.60,
        "drainage":            0.15,
        "aeration":            0.25,
        "compaction_risk":     0.40,
        "typical_ph_range":    {"min": 3.5, "max": 6.0},
        "score_modifiers": {
            "ph":          1.40,   # highly acidic; pH deviation penalised most
            "moisture":    1.35,
            "nitrogen":    0.85,   # organic N not immediately plant-available
            "ec":          0.80,
        },
        "irrigation_frequency_multiplier": 0.6,
        "fertilizer_frequency_multiplier": 0.9,
        "notes": "High organic matter; acidic pH typical 3.5–6.0. "
                 "Lime regularly. Poor aeration limits mineralisation.",
    },

    "silt": {
        "display_name":        "Silt Soil",
        "water_retention":     0.70,
        "nutrient_retention":  0.65,
        "drainage":            0.45,
        "aeration":            0.55,
        "compaction_risk":     0.60,
        "typical_ph_range":    {"min": 6.0, "max": 7.0},
        "score_modifiers": {
            "moisture":    1.10,
            "ec":          1.10,
            "nitrogen":    1.00,
            "phosphorus":  0.95,
        },
        "irrigation_frequency_multiplier": 0.9,
        "fertilizer_frequency_multiplier": 1.0,
        "notes": "Prone to surface crusting; moderate fertility. "
                 "Common in Gangetic delta and river floodplains.",
    },
}

# =============================================================================
# SECTION 7 — WEATHER IMPACT RULES
# =============================================================================

WEATHER_IMPACT_RULES: dict[str, dict[str, Any]] = {

    "high_temperature": {
        "parameter":          "air_temperature",
        "threshold":          38.0,
        "critical_threshold": 45.0,
        "impact_type":        "stress",
        "effects": {
            "moisture":    "accelerated_evapotranspiration",
            "nitrogen":    "volatilisation_risk",
            "microbial":   "reduced_activity_above_40c",
        },
        "alert_code":   "HEAT_STRESS",
        "severity":     "high",
        "action":       "increase_irrigation_frequency",
        "score_penalty": 4,
    },

    "low_temperature": {
        "parameter":          "air_temperature",
        "threshold":          5.0,
        "critical_threshold": -2.0,
        "impact_type":        "stress",
        "effects": {
            "nutrient_uptake": "reduced",
            "microbial":       "dormancy_risk",
            "moisture":        "frost_lock",
        },
        "alert_code":   "FROST_RISK",
        "severity":     "high",
        "action":       "reduce_irrigation_apply_mulch",
        "score_penalty": 4,
    },

    "low_rainfall": {
        "parameter":          "rainfall",
        "threshold":          5.0,
        "critical_threshold": 0.0,
        "impact_type":        "drought",
        "effects": {
            "moisture":    "deficit_likely",
            "ec":          "salt_concentration_risk",
            "nitrogen":    "mobility_reduced",
        },
        "alert_code":   "DROUGHT_RISK",
        "severity":     "medium",
        "action":       "schedule_supplemental_irrigation",
        "score_penalty": 2,
    },

    "high_rainfall": {
        "parameter":          "rainfall",
        "threshold":          80.0,
        "critical_threshold": 150.0,
        "impact_type":        "waterlogging",
        "effects": {
            "moisture":    "waterlogging_risk",
            "nitrogen":    "leaching_and_denitrification",
            "phosphorus":  "runoff_loss",
            "aeration":    "anaerobic_conditions",
        },
        "alert_code":   "WATERLOGGING_RISK",
        "severity":     "high",
        "action":       "improve_drainage_delay_fertiliser",
        "score_penalty": 3,
    },

    "high_humidity": {
        "parameter":          "humidity",
        "threshold":          85.0,
        "critical_threshold": 95.0,
        "impact_type":        "disease",
        "effects": {
            "fungal_risk": "elevated",
            "nitrogen":    "increased_denitrification",
        },
        "alert_code":   "HIGH_HUMIDITY",
        "severity":     "medium",
        "action":       "monitor_fungal_disease_improve_canopy_airflow",
        "score_penalty": 2,
    },

    "low_humidity": {
        "parameter":          "humidity",
        "threshold":          25.0,
        "critical_threshold": 10.0,
        "impact_type":        "desiccation",
        "effects": {
            "moisture":     "rapid_topsoil_evaporation",
            "plant_stress": "transpiration_strain",
        },
        "alert_code":   "LOW_HUMIDITY",
        "severity":     "low",
        "action":       "apply_mulch_increase_irrigation",
        "score_penalty": 1,
    },
}

# =============================================================================
# SECTION 8 — SEASONAL CONFIGURATION
# =============================================================================

SEASONAL_CONFIG: dict[str, dict[str, Any]] = {

    "summer": {
        "months":                    [4, 5, 6, 7, 8, 9],
        "temperature_range":         {"min": 30.0, "max": 45.0},
        "typical_rainfall_mm":       {"weekly_avg": 5.0, "high_event": 60.0},
        "irrigation_multiplier":     1.6,
        "evapotranspiration_index":  "high",
        "nutrient_behavior": {
            "nitrogen":   "rapid_volatilisation_apply_in_evening",
            "phosphorus": "moderate_availability",
            "potassium":  "adequate_mobility",
        },
        "moisture_correction":             -5.0,
        "recommended_fertilizer_timing":   "early_morning_or_evening",
        "risk_factors":                    ["heat_stress", "drought", "nitrogen_loss"],
        "score_modifier":                   0.93,
    },

    "winter": {
        "months":                    [11, 12, 1, 2, 3],
        "temperature_range":         {"min": 5.0, "max": 22.0},
        "typical_rainfall_mm":       {"weekly_avg": 8.0, "high_event": 30.0},
        "irrigation_multiplier":     0.7,
        "evapotranspiration_index":  "low",
        "nutrient_behavior": {
            "nitrogen":   "slow_mineralisation_split_doses",
            "phosphorus": "reduced_uptake_below_10c",
            "potassium":  "adequate",
        },
        "moisture_correction":             +3.0,
        "recommended_fertilizer_timing":   "mid_morning",
        "risk_factors":                    ["frost", "slow_nutrient_uptake"],
        "score_modifier":                   0.96,
    },

    "monsoon": {
        "months":                    [6, 7, 8, 9],
        "temperature_range":         {"min": 24.0, "max": 36.0},
        "typical_rainfall_mm":       {"weekly_avg": 60.0, "high_event": 200.0},
        "irrigation_multiplier":     0.3,
        "evapotranspiration_index":  "moderate",
        "nutrient_behavior": {
            "nitrogen":   "high_leaching_risk_use_slow_release",
            "phosphorus": "runoff_loss_risk",
            "potassium":  "leaching_moderate",
        },
        "moisture_correction":             +8.0,
        "recommended_fertilizer_timing":   "between_rain_events",
        "risk_factors":                    ["waterlogging", "nutrient_leaching", "fungal_disease"],
        "score_modifier":                   0.91,
    },
}

# =============================================================================
# SECTION 9 — ALERT DEFINITIONS
# =============================================================================
# score_impact philosophy (v2.1.0 calibrated):
#   info     →  1–2 pts   (sensor noise; advisory only; not shown to farmer)
#   low      →  3–5 pts   (mild deficiency; monitor)
#   medium   →  5–7 pts   (moderate stress; action within days)
#   high     →  8–11 pts  (significant risk; prompt action)
#   critical → 12–16 pts  (immediate intervention required)
#
# Score profile target:
#   Healthy field (all optimal)          → 90–100
#   1 medium alert                       → 75–88
#   2–3 medium alerts (typical Kharif)   → 55–72   ← daily working range
#   Multiple high alerts                 → 35–54
#   Multi-critical                       → 15–35   ← SCORE_FLOOR = 15
# =============================================================================

ALERT_DEFINITIONS: dict[str, dict[str, Any]] = {

    # ── Nitrogen ──────────────────────────────────────────────────────────────
    "LOW_N": {
        "parameter":     "nitrogen",
        "condition":     "low",
        "base_severity": "medium",
        "message":       "Soil nitrogen below optimal range; crop may show yellowing and stunted growth.",
        "score_impact":  5,
    },
    "CRITICAL_LOW_N": {
        "parameter":     "nitrogen",
        "condition":     "critical_low",
        "base_severity": "critical",
        "message":       "Severe nitrogen deficiency detected; immediate intervention required.",
        "score_impact":  14,
    },
    "HIGH_N": {
        "parameter":     "nitrogen",
        "condition":     "high",
        "base_severity": "medium",
        "message":       "Excess nitrogen present; risk of nitrate leaching and crop burn.",
        "score_impact":  4,
    },
    "CRITICAL_HIGH_N": {
        "parameter":     "nitrogen",
        "condition":     "critical_high",
        "base_severity": "high",
        "message":       "Toxic nitrogen levels detected; apply leaching irrigation or inhibitor.",
        "score_impact":  10,
    },

    # ── Phosphorus ────────────────────────────────────────────────────────────
    "LOW_P": {
        "parameter":     "phosphorus",
        "condition":     "low",
        "base_severity": "medium",
        "message":       "Phosphorus deficiency; root development and flowering at risk.",
        "score_impact":  5,
    },
    "CRITICAL_LOW_P": {
        "parameter":     "phosphorus",
        "condition":     "critical_low",
        "base_severity": "critical",
        "message":       "Severe phosphorus deficiency; plant energy transfer compromised.",
        "score_impact":  13,
    },
    "HIGH_P": {
        "parameter":     "phosphorus",
        "condition":     "high",
        "base_severity": "low",
        "message":       "Elevated phosphorus; may inhibit zinc and iron uptake.",
        "score_impact":  3,
    },

    # ── Potassium ─────────────────────────────────────────────────────────────
    "LOW_K": {
        "parameter":     "potassium",
        "condition":     "low",
        "base_severity": "medium",
        "message":       "Potassium below optimal; water regulation and disease resistance reduced.",
        "score_impact":  5,
    },
    "CRITICAL_LOW_K": {
        "parameter":     "potassium",
        "condition":     "critical_low",
        "base_severity": "critical",
        "message":       "Critical potassium deficiency; fruit and grain quality severely impacted.",
        "score_impact":  13,
    },
    "HIGH_K": {
        "parameter":     "potassium",
        "condition":     "high",
        "base_severity": "low",
        "message":       "Excess potassium; potential antagonism with magnesium and calcium.",
        "score_impact":  3,
    },

    # ── pH ───────────────────────────────────────────────────────────────────
    "LOW_PH": {
        "parameter":     "ph",
        "condition":     "low",
        "base_severity": "medium",
        "message":       "Soil is acidic; nutrient availability and microbial activity reduced.",
        "score_impact":  6,
    },
    "CRITICAL_LOW_PH": {
        "parameter":     "ph",
        "condition":     "critical_low",
        "base_severity": "critical",
        "message":       "Highly acidic soil; aluminium toxicity risk; lime application urgent.",
        "score_impact":  15,
    },
    "HIGH_PH": {
        "parameter":     "ph",
        "condition":     "high",
        "base_severity": "medium",
        "message":       "Alkaline soil; iron, manganese and zinc availability restricted.",
        "score_impact":  6,
    },
    "CRITICAL_HIGH_PH": {
        "parameter":     "ph",
        "condition":     "critical_high",
        "base_severity": "critical",
        "message":       "Severe alkalinity; most micro-nutrients locked out of plant uptake.",
        "score_impact":  14,
    },

    # ── Moisture ──────────────────────────────────────────────────────────────
    "LOW_MOISTURE": {
        "parameter":     "moisture",
        "condition":     "low",
        "base_severity": "medium",
        "message":       "Soil moisture below optimal; water stress and wilting possible.",
        "score_impact":  6,
    },
    "CRITICAL_LOW_MOISTURE": {
        "parameter":     "moisture",
        "condition":     "critical_low",
        "base_severity": "critical",
        "message":       "Severe moisture deficit; wilting and crop failure risk.",
        "score_impact":  16,
    },
    "HIGH_MOISTURE": {
        "parameter":     "moisture",
        "condition":     "high",
        "base_severity": "medium",
        "message":       "Excess soil moisture; anaerobic conditions may damage roots.",
        "score_impact":  5,
    },
    "CRITICAL_HIGH_MOISTURE": {
        "parameter":     "moisture",
        "condition":     "critical_high",
        "base_severity": "critical",
        "message":       "Waterlogging detected; root rot and denitrification risk.",
        "score_impact":  15,
    },

    # ── Electrical Conductivity ───────────────────────────────────────────────
    "HIGH_EC": {
        "parameter":     "ec",
        "condition":     "high",
        "base_severity": "medium",
        "message":       "Elevated salinity detected; osmotic stress limiting water uptake.",
        "score_impact":  6,    # alert fires only above 1.8 dS/m — moderate penalty
    },
    "CRITICAL_HIGH_EC": {
        "parameter":     "ec",
        "condition":     "critical_high",
        "base_severity": "critical",
        "message":       "Toxic salinity level (>4 dS/m); immediate leaching or remediation required.",
        "score_impact":  16,
    },
    "LOW_EC": {
        "parameter":     "ec",
        "condition":     "low",
        "base_severity": "info",
        "message":       "Very low EC; may indicate nutrient-poor or highly leached soil.",
        "score_impact":  2,
    },

    # ── Soil Temperature ──────────────────────────────────────────────────────
    "HIGH_SOIL_TEMP": {
        "parameter":     "temperature",
        "condition":     "high",
        "base_severity": "medium",
        "message":       "Elevated soil temperature; increased evaporation and microbial stress.",
        "score_impact":  3,    # only fires above 35 °C; summer norm in India — kept mild
    },
    "LOW_SOIL_TEMP": {
        "parameter":     "temperature",
        "condition":     "low",
        "base_severity": "medium",
        "message":       "Low soil temperature; reduced nutrient mineralisation and root activity.",
        "score_impact":  3,
    },

    # ── Weather-Triggered ─────────────────────────────────────────────────────
    "HEAT_STRESS": {
        "parameter":     "air_temperature",
        "condition":     "high",
        "base_severity": "high",
        "message":       "Ambient heat stress (>38 °C) impacting transpiration and nutrient uptake.",
        "score_impact":  4,
    },
    "FROST_RISK": {
        "parameter":     "air_temperature",
        "condition":     "low",
        "base_severity": "high",
        "message":       "Near-freezing temperatures detected; frost protection advised.",
        "score_impact":  4,
    },
    "DROUGHT_RISK": {
        "parameter":     "rainfall",
        "condition":     "low",
        "base_severity": "medium",
        "message":       "Insufficient recent rainfall (<5 mm/week); drought risk elevated.",
        "score_impact":  2,
    },
    "WATERLOGGING_RISK": {
        "parameter":     "rainfall",
        "condition":     "high",
        "base_severity": "high",
        "message":       "Heavy rainfall (>80 mm/week) may cause waterlogging; check drainage.",
        "score_impact":  3,
    },
    "HIGH_HUMIDITY": {
        "parameter":     "humidity",
        "condition":     "high",
        "base_severity": "medium",
        "message":       "High humidity (>85%) increases fungal disease risk.",
        "score_impact":  2,
    },
    "LOW_HUMIDITY": {
        "parameter":     "humidity",
        "condition":     "low",
        "base_severity": "low",
        "message":       "Low humidity (<25%) accelerating soil moisture and leaf moisture loss.",
        "score_impact":  1,
    },
}

# =============================================================================
# SECTION 10 — SEVERITY RULES
# =============================================================================
# KEY CALIBRATIONS (v2.1.0):
#
# critical_thresholds.temperature max: 42 → 45 °C
#   Rationale: Sensor at 5–10 cm depth reads 40–43 °C during Indian heat waves
#   in Rajasthan/Vidarbha/Gujarat. Crops (cotton, maize) still growing at these
#   depths. Root-kill threshold is ~45 °C at sensor depth.
#
# multi_issue_overrides — two changes:
#   min_alerts 3 → 4:  A summer Kharif field will routinely have LOW_MOISTURE
#                       + LOW_N + HIGH_SOIL_TEMP simultaneously. These are all
#                       real but individually manageable. 3-alert CRITICAL created
#                       constant emergency alerts all season → alert fatigue.
#   override_severity "critical" → "high": Compound issues warrant urgent action
#                       but CRITICAL is reserved for absolute threshold breaches.
#
# deviation_escalation: 0–15% band = INFO absorbs sensor noise and natural
#   field variation without generating visible alerts.
# =============================================================================

SEVERITY_RULES: dict[str, Any] = {

    "critical_thresholds": {
        # Absolute values → severity auto-escalated to CRITICAL
        "moisture":    {"low": 18.0,  "high": 92.0},
        "ph":          {"low": 4.5,   "high": 8.8},
        "nitrogen":    {"low": 8.0,   "high": 220.0},
        "phosphorus":  {"low": 3.0,   "high": 70.0},
        "potassium":   {"low": 25.0,  "high": 350.0},
        "ec":          {"low": None,  "high": 4.0},    # USDA class III: moderately saline
        "temperature": {"low": 2.0,   "high": 45.0},  # root-kill threshold at sensor depth
    },

    "deviation_escalation": {
        # % deviation from nearest optimal boundary → severity tier
        # 0–15 %  → INFO     captures sensor noise, normal field variation
        # 15–30 % → LOW      mild advisory; monitor but no panic
        # 30–55 % → MEDIUM   action within days
        # 55–80 % → HIGH     prompt action needed; yield risk
        # >80 %   → CRITICAL immediate intervention; severe yield loss
        0.0:  "info",
        15.0: "low",
        30.0: "medium",
        55.0: "high",
        80.0: "critical",
    },

    "multi_issue_overrides": {
        # 4+ concurrent alerts → compound severity upgrade
        "min_alerts_for_override":    4,        # was 3; realistic Indian field threshold
        "override_severity":          "high",   # was "critical"; CRITICAL reserved for extremes
        "message":                    "Multiple concurrent soil health issues detected.",
        "score_penalty_multiplier":   1.20,     # compound amplification; was 1.25
    },

    "extreme_value_override": {
        # Single hard-limit breach → instant CRITICAL regardless of alert count
        "ph_below":       4.2,    # Al + Mn toxicity certain below this
        "ec_above":       6.0,    # lethal salinity for all field crops
        "moisture_below": 10.0,   # permanent wilting point exceeded
        "moisture_above": 96.0,   # complete anaerobic saturation
        "severity":       "critical",
        "score_penalty":  20,
    },

    "severity_rank": {
        "info":     1,
        "low":      2,
        "medium":   3,
        "high":     4,
        "critical": 5,
    },
}

# =============================================================================
# SECTION 11 — FERTILIZER RECOMMENDATION MAP
# =============================================================================

FERTILIZER_RECOMMENDATION_MAP: dict[str, dict[str, Any]] = {

    "LOW_N": {
        "fertilizer":   "urea",
        "display_name": "Urea (46-0-0)",
        "dosage":       "50–80 kg/ha",
        "n_content":    46.0,
        "timing":       "Apply at early vegetative stage; split dose recommended.",
        "method":       "broadcast_and_incorporate",
        "cautions":     ["Avoid surface application in high-temperature conditions.",
                         "Incorporate within 24h to prevent ammonia volatilisation."],
    },
    "CRITICAL_LOW_N": {
        "fertilizer":   "ammonium_sulfate",
        "display_name": "Ammonium Sulphate (21-0-0-24S)",
        "dosage":       "80–120 kg/ha",
        "n_content":    21.0,
        "timing":       "Apply immediately; consider foliar urea 2% as emergency.",
        "method":       "soil_application_with_irrigation",
        "cautions":     ["Monitor pH — ammonium sulfate acidifies soil slightly.",
                         "Follow up with second dose in 14 days."],
    },
    "HIGH_N": {
        "fertilizer":   "none",
        "display_name": "No nitrogen fertilizer",
        "dosage":       "0 kg/ha",
        "timing":       "Withhold all nitrogenous fertilizers until levels normalise.",
        "method":       "withhold",
        "cautions":     ["Consider leaching irrigation if excess is severe.",
                         "Avoid composting nitrogen-rich organic matter."],
    },
    "LOW_P": {
        "fertilizer":   "dap",
        "display_name": "DAP — Di-Ammonium Phosphate (18-46-0)",
        "dosage":       "50–100 kg/ha",
        "p_content":    46.0,
        "timing":       "Basal application at sowing; placed near root zone.",
        "method":       "band_placement",
        "cautions":     ["DAP contributes nitrogen; reduce urea accordingly.",
                         "Effectiveness reduced in highly alkaline soils."],
    },
    "CRITICAL_LOW_P": {
        "fertilizer":   "sspa",
        "display_name": "Single Super Phosphate (0-16-0-11S)",
        "dosage":       "150–200 kg/ha",
        "p_content":    16.0,
        "timing":       "Immediate basal application; follow with foliar MAP spray.",
        "method":       "broadcast_and_incorporate",
        "cautions":     ["Contains sulphur — beneficial for sulphur-deficient soils.",
                         "Multiple split applications preferred."],
    },
    "HIGH_P": {
        "fertilizer":   "none",
        "display_name": "No phosphorus fertilizer",
        "dosage":       "0 kg/ha",
        "timing":       "Withhold phosphatic fertilizers; monitor zinc and iron.",
        "method":       "withhold",
        "cautions":     ["Excess P can lock out Zn and Fe; consider micronutrient check."],
    },
    "LOW_K": {
        "fertilizer":   "mop",
        "display_name": "MOP — Muriate of Potash (0-0-60)",
        "dosage":       "50–80 kg/ha",
        "k_content":    60.0,
        "timing":       "Apply at vegetative to reproductive transition.",
        "method":       "broadcast_and_irrigate",
        "cautions":     ["High chloride — avoid in chloride-sensitive crops.",
                         "Split dose for sandy soils."],
    },
    "CRITICAL_LOW_K": {
        "fertilizer":   "mop",
        "display_name": "MOP — Muriate of Potash (0-0-60)",
        "dosage":       "100–130 kg/ha",
        "k_content":    60.0,
        "timing":       "Immediate application; consider foliar potassium nitrate spray.",
        "method":       "soil_plus_foliar",
        "cautions":     ["Monitor EC after application — MOP raises soil salinity."],
    },
    "HIGH_K": {
        "fertilizer":   "none",
        "display_name": "No potassium fertilizer",
        "dosage":       "0 kg/ha",
        "timing":       "Withhold; check calcium and magnesium for antagonism.",
        "method":       "withhold",
        "cautions":     [],
    },
    "LOW_PH": {
        "fertilizer":   "agricultural_lime",
        "display_name": "Agricultural Lime (CaCO₃)",
        "dosage":       "1.5–4.0 t/ha (based on buffer pH test)",
        "timing":       "Apply 6–8 weeks before planting; incorporate to 15 cm depth.",
        "method":       "deep_incorporation",
        "cautions":     ["Over-liming can cause P and Mn lockout.",
                         "Re-test pH after 6 weeks."],
    },
    "CRITICAL_LOW_PH": {
        "fertilizer":   "dolomitic_lime",
        "display_name": "Dolomitic Lime (CaMg(CO₃)₂)",
        "dosage":       "3.0–6.0 t/ha",
        "timing":       "Apply immediately; multiple passes if above 4.0 t/ha.",
        "method":       "deep_incorporation",
        "cautions":     ["Provides Mg alongside Ca — beneficial for Mg-deficient soils."],
    },
    "HIGH_PH": {
        "fertilizer":   "elemental_sulfur",
        "display_name": "Elemental Sulphur (S⁰)",
        "dosage":       "200–500 kg/ha",
        "timing":       "Apply well before sowing; requires microbial oxidation (4–8 wks).",
        "method":       "broadcast_and_incorporate",
        "cautions":     ["Acidification is slow — plan 1–2 seasons ahead.",
                         "Excessive use will over-acidify."],
    },
    "CRITICAL_HIGH_PH": {
        "fertilizer":   "sulfuric_acid_soil_amendment",
        "display_name": "Gypsum + Elemental Sulphur blend",
        "dosage":       "Gypsum 2 t/ha + Sulphur 400 kg/ha",
        "timing":       "Apply prior to crop season; irrigate well.",
        "method":       "broadcast_and_irrigate",
        "cautions":     ["Consult agronomist before large-scale application."],
    },
    "HIGH_EC": {
        "fertilizer":   "none",
        "display_name": "Leaching irrigation — no fertilizer",
        "dosage":       "Apply 150% irrigation volume to leach salts below root zone.",
        "timing":       "Immediate; irrigate with low-salinity water.",
        "method":       "leaching_irrigation",
        "cautions":     ["Avoid further fertilizer application until EC < 2.0 dS/m."],
    },
    "CRITICAL_HIGH_EC": {
        "fertilizer":   "gypsum",
        "display_name": "Gypsum (CaSO₄·2H₂O) for sodicity correction",
        "dosage":       "2–5 t/ha",
        "timing":       "Apply before deep leaching irrigation.",
        "method":       "broadcast_then_deep_leach",
        "cautions":     ["Use certified low-salinity irrigation water only.",
                         "Consider subsurface drainage if waterlogging persists."],
    },
}

# =============================================================================
# SECTION 12 — SUGGESTION ENGINE
# =============================================================================

SINGLE_ALERT_SUGGESTIONS: dict[str, list[str]] = {
    "LOW_N":                  ["Apply split-dose nitrogen fertilizer.",
                               "Test for sulphur deficiency — often co-occurs with N deficiency."],
    "CRITICAL_LOW_N":         ["Apply nitrogen immediately; consider 2% foliar urea spray.",
                               "Investigate cover crop residue management."],
    "HIGH_N":                 ["Stop all nitrogen applications.",
                               "Schedule leaching irrigation.",
                               "Check recent fertilizer history."],
    "LOW_P":                  ["Apply phosphate fertilizer via band placement near roots.",
                               "Check soil pH — P availability drops below 5.5 and above 7.5."],
    "CRITICAL_LOW_P":         ["Emergency phosphate application required.",
                               "Investigate root health — P deficiency mimics root dysfunction."],
    "HIGH_P":                 ["Test zinc and iron levels.",
                               "Withhold all phosphatic fertilizers this season."],
    "LOW_K":                  ["Apply potassium fertilizer before reproductive stage.",
                               "Check for magnesium excess — Mg can antagonise K uptake."],
    "CRITICAL_LOW_K":         ["Apply MOP immediately; consider foliar potassium spray.",
                               "Check irrigation water K content."],
    "HIGH_K":                 ["Test calcium and magnesium — K excess causes antagonism.",
                               "Withhold potassic fertilizers."],
    "LOW_PH":                 ["Apply agricultural lime; incorporate to root depth.",
                               "Test exchangeable aluminium if pH < 5.0."],
    "CRITICAL_LOW_PH":        ["Urgent liming required.",
                               "Delay planting until pH stabilises.",
                               "Aluminium toxicity test recommended."],
    "HIGH_PH":                ["Apply elemental sulphur to acidify gradually.",
                               "Use acidifying fertilizers (ammonium sulfate)."],
    "CRITICAL_HIGH_PH":       ["Consult soil specialist for reclamation plan.",
                               "Consider sulphuric acid drip fertigation."],
    "LOW_MOISTURE":           ["Schedule irrigation immediately.",
                               "Apply mulch to conserve soil moisture."],
    "CRITICAL_LOW_MOISTURE":  ["Emergency irrigation required.",
                               "Check drip/sprinkler system for failures."],
    "HIGH_MOISTURE":          ["Delay irrigation.",
                               "Improve field drainage."],
    "CRITICAL_HIGH_MOISTURE": ["Install or clear drainage channels.",
                               "Delay all field operations until drained."],
    "HIGH_EC":                ["Apply leaching irrigation with low-salinity water.",
                               "Withhold fertilizers until EC normalises below 2.0 dS/m."],
    "CRITICAL_HIGH_EC":       ["Immediate reclamation programme required.",
                               "Apply gypsum and deep-leach.",
                               "Seek agronomist consultation."],
    "LOW_EC":                 ["Soil may be nutrient-poor; conduct full NPK analysis."],
    "HEAT_STRESS":            ["Increase irrigation frequency.",
                               "Apply light mulch.",
                               "Consider shade nets for sensitive crops."],
    "FROST_RISK":             ["Apply anti-frost cover or mulch.",
                               "Irrigate lightly before frost to release latent heat."],
    "DROUGHT_RISK":           ["Activate supplemental irrigation schedule.",
                               "Monitor moisture sensors hourly."],
    "WATERLOGGING_RISK":      ["Open drainage furrows.",
                               "Delay irrigation events."],
    "HIGH_HUMIDITY":          ["Improve canopy airflow.",
                               "Monitor for fungal lesions."],
    "LOW_HUMIDITY":           ["Apply mulch to slow evaporation.",
                               "Increase irrigation frequency slightly."],
}

MULTI_CONDITION_SUGGESTIONS: list[dict[str, Any]] = [
    {
        "conditions": ["LOW_N", "LOW_PH"],
        "suggestion": "Address soil acidity first — lime application will improve nitrogen "
                      "availability before adding N fertilizer.",
        "priority":   "high",
    },
    {
        "conditions": ["HIGH_EC", "HIGH_N"],
        "suggestion": "Excess salinity and nitrogen co-detected. Leach field before any "
                      "fertilizer application. Both issues share the same corrective action.",
        "priority":   "critical",
    },
    {
        "conditions": ["LOW_MOISTURE", "HIGH_EC"],
        "suggestion": "Low moisture concentrates salts. Irrigate slowly to both rehydrate "
                      "and leach salts simultaneously.",
        "priority":   "high",
    },
    {
        "conditions": ["HIGH_MOISTURE", "LOW_N"],
        "suggestion": "Waterlogging causes nitrogen denitrification loss. Drain field before "
                      "N application; use slow-release urea.",
        "priority":   "high",
    },
    {
        "conditions": ["LOW_P", "HIGH_PH"],
        "suggestion": "High pH locks phosphorus as calcium-phosphate complexes. "
                      "Acidify soil with sulphur before phosphate application.",
        "priority":   "medium",
    },
    {
        "conditions": ["LOW_K", "HIGH_EC"],
        "suggestion": "MOP (potash) contains chloride which raises EC. "
                      "Use Sulphate of Potash (SOP) as a low-chloride alternative.",
        "priority":   "high",
    },
    {
        "conditions": ["HEAT_STRESS", "LOW_MOISTURE"],
        "suggestion": "Combined heat and drought: switch to night-time drip irrigation "
                      "to maximise water use efficiency and reduce evaporation.",
        "priority":   "critical",
    },
    {
        "conditions": ["HIGH_HUMIDITY", "HIGH_MOISTURE"],
        "suggestion": "Disease-conducive conditions: reduce irrigation, improve drainage, "
                      "and apply preventive fungicide.",
        "priority":   "high",
    },
    {
        "conditions": ["LOW_N", "LOW_P", "LOW_K"],
        "suggestion": "Macro-nutrient trifecta deficiency: apply a balanced NPK complex "
                      "fertilizer (e.g., 20-20-20) immediately.",
        "priority":   "critical",
    },
    {
        "conditions": ["CRITICAL_LOW_N", "DROUGHT_RISK"],
        "suggestion": "Nitrogen deficiency under drought: foliar urea spray (2%) is more "
                      "effective than soil application under dry conditions.",
        "priority":   "critical",
    },
]

# =============================================================================
# SECTION 13 — CONFLICT DETECTION MAP
# =============================================================================

CONFLICT_DETECTION_MAP: dict[str, dict[str, Any]] = {
    "urea": {
        "expected_fix":          ["LOW_N"],
        "expected_window":       14,
        "conflict_if_present":   ["HIGH_PH", "WATERLOGGING_RISK"],
        "conflict_reason":       "Urea hydrolysis inhibited in waterlogged/alkaline soils.",
        "alternative":           "ammonium_sulfate",
    },
    "dap": {
        "expected_fix":          ["LOW_P", "LOW_N"],
        "expected_window":       21,
        "conflict_if_present":   ["CRITICAL_HIGH_PH"],
        "conflict_reason":       "Phosphate becomes insoluble (Ca-P) above pH 7.5.",
        "alternative":           "sspa",
    },
    "mop": {
        "expected_fix":          ["LOW_K"],
        "expected_window":       14,
        "conflict_if_present":   ["HIGH_EC"],
        "conflict_reason":       "MOP contains chloride which elevates EC.",
        "alternative":           "potassium_sulfate",
    },
    "sspa": {
        "expected_fix":          ["LOW_P"],
        "expected_window":       21,
        "conflict_if_present":   ["LOW_PH"],
        "conflict_reason":       "SSP sulphur may further acidify already acidic soil.",
        "alternative":           "rock_phosphate_with_lime",
    },
    "ammonium_sulfate": {
        "expected_fix":          ["LOW_N"],
        "expected_window":       10,
        "conflict_if_present":   ["LOW_PH", "CRITICAL_LOW_PH"],
        "conflict_reason":       "Ammonium sulphate acidifies soil; worsens low pH.",
        "alternative":           "calcium_ammonium_nitrate",
    },
    "agricultural_lime": {
        "expected_fix":          ["LOW_PH", "CRITICAL_LOW_PH"],
        "expected_window":       42,
        "conflict_if_present":   ["HIGH_PH"],
        "conflict_reason":       "Lime application on already alkaline soil further raises pH.",
        "alternative":           "elemental_sulfur",
    },
    "elemental_sulfur": {
        "expected_fix":          ["HIGH_PH", "CRITICAL_HIGH_PH"],
        "expected_window":       56,
        "conflict_if_present":   ["LOW_PH"],
        "conflict_reason":       "Further acidification will breach critical pH floor.",
        "alternative":           "gypsum",
    },
    "organic_compost": {
        "expected_fix":          ["LOW_N", "LOW_P", "LOW_K", "LOW_EC"],
        "expected_window":       30,
        "conflict_if_present":   ["CRITICAL_HIGH_EC"],
        "conflict_reason":       "Compost salts can temporarily raise EC in already saline soils.",
        "alternative":           "vermicompost_low_salt",
    },
    "npk_complex": {
        "expected_fix":          ["LOW_N", "LOW_P", "LOW_K"],
        "expected_window":       14,
        "conflict_if_present":   ["HIGH_EC", "HIGH_N"],
        "conflict_reason":       "NPK complex worsens existing EC or N excess.",
        "alternative":           "targeted_single_nutrient_application",
    },
}

# =============================================================================
# SECTION 14 — SCORING SYSTEM
# =============================================================================

SCORE_WEIGHTS: dict[str, float] = {
    "moisture":    0.20,
    "ph":          0.15,
    "nitrogen":    0.18,
    "phosphorus":  0.12,
    "potassium":   0.12,
    "ec":          0.10,
    "temperature": 0.08,
    "humidity":    0.05,
}

CROP_SCORE_WEIGHT_OVERRIDES: dict[str, dict[str, float]] = {
    "rice": {
        "moisture":    0.28,
        "ph":          0.16,
        "nitrogen":    0.16,
        "potassium":   0.13,
        "ec":          0.07,
    },
    "cotton": {
        "potassium":   0.20,
        "moisture":    0.18,
        "ph":          0.14,
        "nitrogen":    0.15,
        "ec":          0.08,
    },
    "sugarcane": {
        "nitrogen":    0.20,
        "potassium":   0.18,
        "moisture":    0.22,
        "ph":          0.12,
        "ec":          0.08,
    },
    "potato": {
        "potassium":   0.20,
        "ph":          0.18,
        "moisture":    0.20,
        "temperature": 0.12,
        "nitrogen":    0.15,
    },
    "soybean": {
        "ph":          0.18,
        "phosphorus":  0.16,
        "moisture":    0.18,
        "nitrogen":    0.12,
    },
}

SCORE_BANDS: dict[str, dict[str, Any]] = {
    "excellent": {"min": 85, "max": 100, "label": "Excellent",  "color": "#2ecc71"},
    "good":      {"min": 70, "max": 84,  "label": "Good",       "color": "#27ae60"},
    "fair":      {"min": 50, "max": 69,  "label": "Fair",       "color": "#f39c12"},
    "poor":      {"min": 30, "max": 49,  "label": "Poor",       "color": "#e67e22"},
    "critical":  {"min": 0,  "max": 29,  "label": "Critical",   "color": "#e74c3c"},
}

SCORE_BASELINE: int = 100   # subtract penalties from this

# Hard minimum score — prevents physically impossible outputs (e.g., 3–10%)
# Any living crop field retains residual health; 15 is the floor.
# Usage: final_score = max(SCORE_FLOOR, SCORE_BASELINE - total_penalty)
SCORE_FLOOR: int = 15

# =============================================================================
# SECTION 15 — SUMMARY FRAGMENTS
# =============================================================================

SUMMARY_FRAGMENTS: dict[str, str] = {
    "LOW_N":                  "nitrogen deficiency detected",
    "CRITICAL_LOW_N":         "critical nitrogen shortage — immediate intervention required",
    "HIGH_N":                 "excess nitrogen present",
    "CRITICAL_HIGH_N":        "toxic nitrogen levels detected",
    "LOW_P":                  "phosphorus below optimal levels",
    "CRITICAL_LOW_P":         "severe phosphorus deficiency",
    "HIGH_P":                 "phosphorus accumulation noted",
    "LOW_K":                  "potassium shortage detected",
    "CRITICAL_LOW_K":         "critical potassium deficiency",
    "HIGH_K":                 "excess potassium in soil",
    "LOW_PH":                 "soil acidity above tolerance",
    "CRITICAL_LOW_PH":        "critically acidic soil conditions",
    "HIGH_PH":                "soil alkalinity elevated",
    "CRITICAL_HIGH_PH":       "severe soil alkalinity — nutrient lockout risk",
    "LOW_MOISTURE":           "soil moisture below threshold",
    "CRITICAL_LOW_MOISTURE":  "severe moisture deficit — crop stress imminent",
    "HIGH_MOISTURE":          "excess soil water detected",
    "CRITICAL_HIGH_MOISTURE": "waterlogging conditions present",
    "HIGH_EC":                "elevated soil salinity",
    "CRITICAL_HIGH_EC":       "toxic salinity levels detected",
    "LOW_EC":                 "very low soil ionic activity",
    "HIGH_SOIL_TEMP":         "elevated soil surface temperature",
    "LOW_SOIL_TEMP":          "sub-optimal soil temperature",
    "HEAT_STRESS":            "ambient heat stress conditions",
    "FROST_RISK":             "frost risk from low air temperature",
    "DROUGHT_RISK":           "drought risk from low recent rainfall",
    "WATERLOGGING_RISK":      "waterlogging risk from heavy rainfall",
    "HIGH_HUMIDITY":          "high humidity — fungal risk elevated",
    "LOW_HUMIDITY":           "low humidity — evaporation rate elevated",
}

SUMMARY_TEMPLATES: dict[str, str] = {
    "no_alerts":    "Soil health is {score_label}. All parameters are within optimal range for {crop_type}.",
    "single_alert": "Soil health is {score_label} (score: {score}/100). Issue detected: {alert_fragment}. Recommendation: {recommendation}.",
    "multi_alert":  "Soil health score is {score}/100 ({score_label}). {alert_count} issues detected: {alert_list}. Priority action: {top_recommendation}.",
    "critical":     "⚠ CRITICAL soil health status (score: {score}/100). Immediate action required. Primary concern: {primary_alert}. Contact agronomist.",
}

# =============================================================================
# SECTION 16 — OPTIONAL FIELDS (Data Quality Scoring)
# =============================================================================

OPTIONAL_FIELDS: dict[str, dict[str, Any]] = {
    "growth_stage": {
        "weight":      0.10,
        "description": "Enables stage-specific nutrient requirement adjustments.",
        "impact":      "Crop-specific optimal ranges shift with growth stage.",
    },
    "season": {
        "weight":      0.10,
        "description": "Activates seasonal config modifiers for irrigation and nutrients.",
        "impact":      "Irrigation multiplier and nutrient behaviour rules applied.",
    },
    "fertilizer": {
        "weight":      0.12,
        "description": "Enables conflict detection between applied and needed fertilizer.",
        "impact":      "Conflict detection map activated.",
    },
    "rainfall": {
        "weight":      0.08,
        "description": "Enables weather impact rules for drought and waterlogging.",
        "impact":      "Weather impact alerts activated.",
    },
    "irrigation": {
        "weight":      0.06,
        "description": "Contextualises moisture readings with applied water.",
        "impact":      "Moisture alerts adjusted for recent irrigation.",
    },
    "region": {
        "weight":      0.04,
        "description": "Future: region-specific calibration models.",
        "impact":      "Reserved for ML feature engineering.",
    },
    "field_id": {
        "weight":      0.03,
        "description": "Enables historical trend comparison per field.",
        "impact":      "Time-series anomaly detection (future feature).",
    },
}

DATA_QUALITY_THRESHOLDS: dict[str, Any] = {
    "required_fields": SOIL_PARAMETERS + AIR_PARAMETERS,
    "optional_fields": list(OPTIONAL_FIELDS.keys()),
    "quality_bands": {
        "high":   {"min": 0.85, "label": "High Confidence"},
        "medium": {"min": 0.60, "label": "Moderate Confidence"},
        "low":    {"min": 0.00, "label": "Low Confidence — Increase Sensor Coverage"},
    },
}

# =============================================================================
# SECTION 17 — ALERT DISPLAY CONFIGURATION  (new in v2.1.0)
# =============================================================================
# INFO-severity alerts are near-boundary advisories caused by sensor noise
# or readings at the edge of normal variation.  They should:
#   (a) NOT appear in the farmer-facing alert list (suppress_info_in_alert_list)
#   (b) Still contribute a dampened score penalty (40% of full impact)
#   (c) Still be logged for system debugging (log_info_alerts)
#
# This prevents UX alert fatigue while retaining subtle scoring sensitivity.
#
# Usage in service.py (example):
#   for alert in raw_alerts:
#       if alert["severity"] == "info":
#           penalty = alert["score_impact"] * ALERT_DISPLAY_CONFIG["info_score_impact_multiplier"]
#           if not ALERT_DISPLAY_CONFIG["suppress_info_in_alert_list"]:
#               farmer_alerts.append(alert)
#       else:
#           penalty = alert["score_impact"]
#           farmer_alerts.append(alert)
# =============================================================================

ALERT_DISPLAY_CONFIG: dict[str, Any] = {
    "suppress_info_in_alert_list":  True,   # INFO → invisible to farmer
    "info_score_impact_multiplier": 0.4,    # 40% of score_impact applied for INFO
    "min_severity_for_display":     "low",  # lowest visible severity tier
    "log_info_alerts":              True,   # still written to system logs
}

# =============================================================================
# SECTION 18 — AGENT COMMUNICATION PROTOCOL
# =============================================================================

AGENT_COMMUNICATION: dict[str, Any] = {
    "output_topics": {
        "alerts":          "soil.alerts",
        "recommendations": "soil.recommendations",
        "score":           "soil.score",
        "summary":         "soil.summary",
        "raw_analysis":    "soil.analysis.raw",
    },
    "input_topics": {
        "sensor_data":     "sensors.soil",
        "weather_data":    "sensors.weather",
        "context_data":    "context.field",
    },
    "downstream_agents": {
        "irrigation_agent": {"trigger_alerts": ["LOW_MOISTURE", "CRITICAL_LOW_MOISTURE", "DROUGHT_RISK"]},
        "fertilizer_agent": {"trigger_alerts": ["LOW_N", "CRITICAL_LOW_N", "LOW_P",
                                                "CRITICAL_LOW_P", "LOW_K", "CRITICAL_LOW_K"]},
        "disease_agent":    {"trigger_alerts": ["HIGH_HUMIDITY", "WATERLOGGING_RISK", "HIGH_MOISTURE"]},
        "reporting_agent":  {"trigger_alerts": "__all__"},
    },
    "response_timeout_ms": 5000,
    "retry_attempts":      3,
    "priority_levels":     {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4},
}

# =============================================================================
# SECTION 19 — API & RUNTIME CONFIGURATION
# =============================================================================

API_CONFIG: dict[str, Any] = {
    "host":              "0.0.0.0",
    "port":              8001,
    "prefix":            "/api/v1/soil-agent",
    "docs_url":          "/docs",
    "redoc_url":         "/redoc",
    "openapi_url":       "/openapi.json",
    "allowed_origins":   ["*"],   # Tighten in production
    "request_timeout_s": 30,
}

CACHE_CONFIG: dict[str, Any] = {
    "enabled":              True,
    "backend":              "redis",
    "ttl_seconds":          300,
    "analysis_cache_key":   "soil_analysis:{field_id}:{timestamp_bucket}",
    "invalidate_on_update": True,
}

LOGGING_CONFIG: dict[str, Any] = {
    "level":          "INFO",
    "format":         "json",
    "include_fields": ["agent_id", "field_id", "crop_type", "score", "alert_count"],
    "sensitive_fields": [],
    "output":         "stdout",
}

# =============================================================================
# SECTION 20 — ML INTEGRATION HOOKS (Future-Ready)
# =============================================================================

ML_CONFIG: dict[str, Any] = {
    "enabled":                  False,
    "feature_columns":          SOIL_PARAMETERS + AIR_PARAMETERS + [
                                    "soil_type", "crop_type", "season", "growth_stage"
                                ],
    "target_columns":           ["health_score", "primary_alert", "yield_risk_index"],
    "model_registry_url":       "http://model-registry:8080/v1/models",
    "inference_endpoint":       "http://inference-service:8082/predict/soil",
    "fallback_to_rule_engine":  True,
    "confidence_threshold":     0.75,
    "feature_importance_map": {
        "ph":          0.18,
        "nitrogen":    0.16,
        "moisture":    0.15,
        "potassium":   0.13,
        "phosphorus":  0.12,
        "ec":          0.10,
        "temperature": 0.09,
        "humidity":    0.07,
    },
}

# =============================================================================
# END OF CONFIG — v2.1.0
# =============================================================================