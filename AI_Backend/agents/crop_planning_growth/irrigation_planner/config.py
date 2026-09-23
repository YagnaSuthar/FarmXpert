"""
Irrigation Planner Agent — Configuration
=========================================
Every agronomic constant lives here, and each table names its source.
Service code reads these tables only — it never hardcodes a threshold.

Sources
  FAO-56   Allen, Pereira, Raes & Smith (1998), Crop evapotranspiration.
           Table 11 (stage lengths), 12 (Kc), 19 (soil water), 22 (root
           depth Zr and depletion fraction p).
  FAO-29   Ayers & Westcot (1985), Water quality for agriculture — the
           leaching requirement.
  Maas & Hoffman (1977) / Maas (1984) — crop salt tolerance: yield holds
           until soil ECe passes a threshold, then falls by a fixed % per dS/m.
  Application efficiencies: FAO Irrigation Water Management manual 4 and
           ICID typical field values.
"""

from __future__ import annotations

from typing import Final


# ── Agent identity ──────────────────────────────────────────────────────────

AGENT_ID:      Final[str] = "irrigation_agent"
AGENT_VERSION: Final[str] = "3.0.0"
AGENT_NAME:    Final[str] = "Irrigation Planner"


# ── Decision codes (machine-parseable; orchestrator humanises) ───────────────

class Decision:
    IRRIGATE             = "IRRIGATE"
    SKIP_RAIN            = "SKIP_RAIN"                # likely rain covers the depletion
    SKIP_SATURATED       = "SKIP_SATURATED"           # root zone at / near field capacity
    SKIP_DEFICIT_SMALL   = "SKIP_DEFICIT_SMALL"       # depletion within readily available water
    POSTPONE_STORM       = "POSTPONE_STORM"           # heavy rain likely — do not add water
    POSTPONE_HEAT        = "POSTPONE_HEAT"            # (reserved) apply at night instead
    REDUCE_WET           = "REDUCE_WET"               # (reserved) top-up only
    EMERGENCY_IRRIGATE   = "EMERGENCY_IRRIGATE"       # approaching the wilting point
    MAINTAIN_FLOOD       = "MAINTAIN_FLOOD"           # paddy: keep standing water
    DRAIN_FIELD          = "DRAIN_FIELD"              # paddy: drainage phase
    POSTPONE_FROZEN      = "POSTPONE_FROZEN"          # ground frozen - water cannot infiltrate
    SKIP_CROP_MATURE     = "SKIP_CROP_MATURE"         # dry-down before harvest


# ── Reason codes — surfaced to the farmer via the orchestrator ──────────────

class Reason:
    SOIL_BELOW_TARGET      = "SOIL_BELOW_TARGET"          # depletion passed RAW
    SOIL_BELOW_WILTING     = "SOIL_BELOW_WILTING"         # depletion near TAW (wilting)
    SOIL_NEAR_FC           = "SOIL_NEAR_FC"               # root zone near field capacity
    RAIN_FORECAST          = "RAIN_FORECAST"              # likely rain covers depletion
    STORM_FORECAST         = "STORM_FORECAST"
    HIGH_ET_HEAT           = "HIGH_ET_HEAT"
    LOW_ET                 = "LOW_ET"
    CROP_CRITICAL_STAGE    = "CROP_CRITICAL_STAGE"        # stricter depletion limit
    CROP_KC_LOW            = "CROP_KC_LOW"
    PADDY_FLOOD_MAINTAIN   = "PADDY_FLOOD_MAINTAIN"
    PADDY_DRAINAGE_PHASE   = "PADDY_DRAINAGE_PHASE"
    SOIL_TYPE_FAST_DRAIN   = "SOIL_TYPE_FAST_DRAIN"
    SOIL_TYPE_SLOW_DRAIN   = "SOIL_TYPE_SLOW_DRAIN"
    SALINITY_LEACHING      = "SALINITY_LEACHING"          # leaching fraction added
    DEFICIT_BELOW_MIN      = "DEFICIT_BELOW_MIN"          # depletion within RAW
    WIND_SPRAY_LIMIT       = "WIND_SPRAY_LIMIT"           # sprinkler unsuitable in wind
    SPLIT_APPLICATION      = "SPLIT_APPLICATION"          # dose longer than one working day
    FROZEN_SOIL            = "FROZEN_SOIL"
    CROP_MATURE            = "CROP_MATURE"


# ── Operational thresholds ──────────────────────────────────────────────────

MIN_EVENT_MM:            Final[float] = 5.0    # smallest net irrigation worth an event
MAX_IRRIGATION_HOURS:    Final[float] = 8.0    # one set per working day
EMERGENCY_DEPLETION:     Final[float] = 0.9    # Dr >= 90 % of TAW: close to wilting
NEAR_FC_DEPLETION:       Final[float] = 0.1    # Dr <= 10 % of TAW: soil near capacity
# Stress-sensitive stages: FAO-56 advises a smaller p; 20 % tighter.
CRITICAL_STAGE_P_FACTOR: Final[float] = 0.8
# Rain the soil actually takes in: CROPWAT "fixed percentage" default (80 %),
# and half of anything beyond 50 mm/day, which mostly runs off.
RAIN_EFFECTIVE_FRACTION: Final[float] = 0.8
RAIN_RUNOFF_ABOVE_MM:    Final[float] = 50.0
# Rain counted as likely enough to wait for (skip irrigating before it).
RAIN_LIKELY_PERCENT:     Final[float] = 60.0
RAIN_WAIT_DAYS:          Final[int]   = 2
# IMD "heavy rain" (24 h) — never add irrigation water ahead of it.
STORM_POSTPONE_MM:       Final[float] = 64.5
HIGH_TEMP_C:             Final[float] = 38.0
HIGH_WIND_KMH:           Final[float] = 15.0   # sprinkler drift / uneven application
# Daytime maximum at or below this: the topsoil stays frozen, water ponds or
# ices instead of infiltrating, sprinkler lines freeze, the crop is not
# transpiring. Irrigate only once it thaws.
FROZEN_SOIL_TMAX_C:      Final[float] = 2.0
# Days after sowing this far past the typical season is probably a wrong
# sowing date - the crop should already be harvested.
PAST_SEASON_FACTOR:      Final[float] = 1.25

DEFAULT_ROOT_DEPTH_M:    Final[float] = 0.6


# ── Irrigation methods ──────────────────────────────────────────────────────
# rate_mm_h:  typical net application rate on the field
# efficiency: application efficiency Ea — the share of water applied that
#             reaches the root zone (surface ~50-70 %, sprinkler ~75 %, drip ~90 %)

METHODS = {
    "drip":         {"rate_mm_h": 3.0,  "efficiency": 0.90},
    "sprinkler":    {"rate_mm_h": 10.0, "efficiency": 0.75},
    "center_pivot": {"rate_mm_h": 8.0,  "efficiency": 0.85},
    "furrow":       {"rate_mm_h": 20.0, "efficiency": 0.60},
    "border":       {"rate_mm_h": 25.0, "efficiency": 0.65},
    "basin":        {"rate_mm_h": 30.0, "efficiency": 0.70},
    "flood":        {"rate_mm_h": 30.0, "efficiency": 0.50},
}
# Savings are reported against flood irrigation of the same crop need.
BASELINE_METHOD: Final[str] = "flood"

# Kept for callers that read the old table.
METHOD_FLOW_RATES = {m: v["rate_mm_h"] for m, v in METHODS.items()}


# =============================================================================
# CROPS
# =============================================================================
# kc_by_stage   FAO-56 Table 12 (ini / mid / end) spread over named stages
# root_depth_m  effective rooting depth for scheduling, FAO-56 Table 22
# p             FAO-56 Table 22 depletion fraction before stress (ETc 5 mm/d)
# season_days   FAO-56 Table 11 typical length, and stage shares for mapping
#               days-after-sowing onto a stage
# salinity      Maas-Hoffman threshold ECe (dS/m) and yield loss % per dS/m
#               above it; None where no published value exists
# water_management  "upland" (depletion-based) | "paddy" (standing water)
# =============================================================================

CROP_CONFIG: dict = {

    "wheat": {
        "dry_down_at_maturity": True,
        "display_name": "Wheat", "water_management": "upland",
        "root_depth_m": 0.9, "p": 0.55, "season_days": 120,
        "preferred_methods": ["sprinkler", "border", "basin"],
        "discouraged_methods": ["drip"],
        "kc_by_stage": {"germination": 0.4, "seedling": 0.5, "vegetative": 0.7,
                        "flowering": 1.15, "fruiting": 1.10, "maturation": 0.7,
                        "harvest_ready": 0.4},
        "critical_stages": ["flowering", "fruiting"],
        "salinity": {"threshold": 6.0, "slope": 7.1},
        "notes": "Crown-root initiation (~21 days) and flowering are the irrigations "
                 "never to miss. Avoid waterlogging.",
    },

    "rice": {
        "display_name": "Rice (Paddy)", "water_management": "paddy",
        "root_depth_m": 0.5, "p": 0.20, "season_days": 150,
        "preferred_methods": ["basin", "flood"],
        "discouraged_methods": ["drip", "sprinkler"],
        "kc_by_stage": {"germination": 1.05, "seedling": 1.10, "vegetative": 1.20,
                        "flowering": 1.20, "fruiting": 1.20, "maturation": 0.90,
                        "harvest_ready": 0.60},
        "critical_stages": ["vegetative", "flowering"],
        "standing_water_mm": {"min": 50.0, "target": 75.0, "max": 100.0},
        "drainage_stages": ["panicle_initiation", "harvest_ready"],
        "salinity": {"threshold": 3.0, "slope": 12.0},
        "notes": "Keep 50-100 mm standing water; drain 10-15 days before harvest. "
                 "Alternate wetting and drying saves 15-30 % water without yield loss.",
    },

    "maize": {
        "dry_down_at_maturity": True,
        "display_name": "Maize", "water_management": "upland",
        "root_depth_m": 0.9, "p": 0.55, "season_days": 125,
        "preferred_methods": ["furrow", "sprinkler", "drip"],
        "discouraged_methods": ["flood"],
        "kc_by_stage": {"germination": 0.4, "seedling": 0.6, "vegetative": 0.85,
                        "flowering": 1.20, "fruiting": 1.15, "maturation": 0.80,
                        "harvest_ready": 0.5},
        "critical_stages": ["flowering", "fruiting"],
        "salinity": {"threshold": 1.7, "slope": 12.0},
        "notes": "Tasselling and silking are the most sensitive stages.",
    },

    "cotton": {
        "dry_down_at_maturity": True,
        "display_name": "Cotton", "water_management": "upland",
        "root_depth_m": 1.2, "p": 0.65, "season_days": 180,
        "preferred_methods": ["drip", "furrow"],
        "discouraged_methods": ["flood"],
        "kc_by_stage": {"germination": 0.35, "seedling": 0.5, "vegetative": 0.75,
                        "flowering": 1.15, "fruiting": 1.20, "maturation": 0.85,
                        "harvest_ready": 0.55},
        "critical_stages": ["flowering", "fruiting"],
        "salinity": {"threshold": 7.7, "slope": 5.2},
        "notes": "Deep roots tolerate moderate deficit. Square formation to boll "
                 "development is the critical window; stress then sheds bolls.",
    },

    "sugarcane": {
        "dry_down_at_maturity": True,
        "display_name": "Sugarcane", "water_management": "upland",
        "root_depth_m": 1.5, "p": 0.65, "season_days": 365,
        "preferred_methods": ["drip", "furrow"],
        "discouraged_methods": [],
        "kc_by_stage": {"germination": 0.4, "seedling": 0.6, "vegetative": 0.85,
                        "flowering": 1.25, "fruiting": 1.25, "maturation": 0.95,
                        "harvest_ready": 0.60},
        "critical_stages": ["vegetative", "flowering"],
        "salinity": {"threshold": 1.7, "slope": 5.9},
        "notes": "High seasonal demand; drip saves 30-50 % water over furrow.",
    },

    "soybean": {
        "dry_down_at_maturity": True,
        "display_name": "Soybean", "water_management": "upland",
        "root_depth_m": 0.8, "p": 0.50, "season_days": 115,
        "preferred_methods": ["sprinkler", "furrow"],
        "discouraged_methods": ["flood"],
        "kc_by_stage": {"germination": 0.4, "seedling": 0.6, "vegetative": 0.75,
                        "flowering": 1.15, "fruiting": 1.15, "maturation": 0.75,
                        "harvest_ready": 0.5},
        "critical_stages": ["flowering", "fruiting"],
        "salinity": {"threshold": 5.0, "slope": 20.0},
        "notes": "Pod filling is the critical stage. Waterlogging causes root rot.",
    },

    "potato": {
        "dry_down_at_maturity": True,
        "display_name": "Potato", "water_management": "upland",
        "root_depth_m": 0.5, "p": 0.35, "season_days": 105,
        "preferred_methods": ["drip", "sprinkler", "furrow"],
        "discouraged_methods": ["flood"],
        "kc_by_stage": {"germination": 0.5, "seedling": 0.6, "vegetative": 0.85,
                        "flowering": 1.15, "fruiting": 1.15, "maturation": 0.75,
                        "harvest_ready": 0.5},
        "critical_stages": ["flowering", "fruiting"],
        "salinity": {"threshold": 1.7, "slope": 12.0},
        "notes": "Shallow roots and a low p: frequent light irrigations. Stress during "
                 "tuber bulking causes misshapen and cracked tubers.",
    },

    "tomato": {
        "display_name": "Tomato", "water_management": "upland",
        "root_depth_m": 0.7, "p": 0.40, "season_days": 145,
        "preferred_methods": ["drip", "furrow"],
        "discouraged_methods": ["flood", "sprinkler"],
        "kc_by_stage": {"germination": 0.6, "seedling": 0.6, "vegetative": 0.85,
                        "flowering": 1.15, "fruiting": 1.15, "maturation": 0.85,
                        "harvest_ready": 0.7},
        "critical_stages": ["flowering", "fruiting"],
        "salinity": {"threshold": 2.5, "slope": 9.9},
        "notes": "Drip strongly preferred - wet foliage spreads early blight. Irregular "
                 "watering causes blossom-end rot and fruit cracking.",
    },

    # ── Crops the crop-prediction agent recommends for Gujarat ────────────
    "groundnut": {
        "dry_down_at_maturity": True,
        "display_name": "Groundnut", "water_management": "upland",
        "root_depth_m": 0.75, "p": 0.50, "season_days": 130,
        "preferred_methods": ["sprinkler", "drip", "furrow"],
        "discouraged_methods": ["flood"],
        "kc_by_stage": {"germination": 0.4, "seedling": 0.45, "vegetative": 0.75,
                        "flowering": 1.15, "fruiting": 1.15, "maturation": 0.8,
                        "harvest_ready": 0.6},
        "critical_stages": ["flowering", "fruiting"],
        "salinity": {"threshold": 3.2, "slope": 29.0},
        "notes": "Pegging and pod development are critical - keep the top soil moist "
                 "so pegs can enter. Avoid water at harvest.",
    },

    "guar": {
        "dry_down_at_maturity": True,
        "display_name": "Guar (Cluster Bean)", "water_management": "upland",
        "root_depth_m": 0.75, "p": 0.55, "season_days": 110,
        "preferred_methods": ["sprinkler", "furrow"],
        "discouraged_methods": ["flood"],
        "kc_by_stage": {"germination": 0.4, "seedling": 0.45, "vegetative": 0.75,
                        "flowering": 1.10, "fruiting": 1.05, "maturation": 0.55,
                        "harvest_ready": 0.35},
        "critical_stages": ["flowering"],
        "salinity": {"threshold": 8.8, "slope": 17.0},
        "notes": "Drought-hardy and salt-tolerant; one irrigation at flowering in a dry "
                 "spell protects yield. Very sensitive to waterlogging.",
    },

    "white peas": {
        "dry_down_at_maturity": True,
        "display_name": "White Peas", "water_management": "upland",
        "root_depth_m": 0.8, "p": 0.40, "season_days": 115,
        "preferred_methods": ["sprinkler", "furrow"],
        "discouraged_methods": ["flood"],
        "kc_by_stage": {"germination": 0.5, "seedling": 0.55, "vegetative": 0.85,
                        "flowering": 1.15, "fruiting": 1.10, "maturation": 0.6,
                        "harvest_ready": 0.3},
        "critical_stages": ["flowering", "fruiting"],
        "salinity": {"threshold": 3.4, "slope": 10.6},
        "notes": "Flowering and pod filling are critical. Light irrigations; peas "
                 "suffer quickly from waterlogging.",
    },

    "coriander": {
        "display_name": "Coriander", "water_management": "upland",
        "root_depth_m": 0.4, "p": 0.35, "season_days": 55,
        "preferred_methods": ["sprinkler", "drip"],
        "discouraged_methods": ["flood"],
        "kc_by_stage": {"germination": 0.7, "seedling": 0.7, "vegetative": 0.9,
                        "flowering": 1.05, "fruiting": 1.05, "maturation": 0.95,
                        "harvest_ready": 0.95},
        "critical_stages": ["vegetative"],
        "salinity": None,
        "notes": "Shallow-rooted leafy crop: light, frequent irrigation for tender "
                 "leaves (FAO-56 small-vegetable coefficients).",
    },

    "ajwain": {
        "dry_down_at_maturity": True,
        "display_name": "Ajwain", "water_management": "upland",
        "root_depth_m": 0.6, "p": 0.45, "season_days": 165,
        "preferred_methods": ["furrow", "sprinkler", "drip"],
        "discouraged_methods": ["flood"],
        "kc_by_stage": {"germination": 0.5, "seedling": 0.55, "vegetative": 0.8,
                        "flowering": 1.05, "fruiting": 1.0, "maturation": 0.7,
                        "harvest_ready": 0.5},
        "critical_stages": ["flowering", "fruiting"],
        "salinity": None,
        "notes": "Seed spice; irrigate at flowering and seed formation. Excess water "
                 "at seed ripening lowers oil content.",
    },

    "mango": {
        "display_name": "Mango (orchard)", "water_management": "upland",
        "root_depth_m": 1.5, "p": 0.50, "season_days": None,
        "preferred_methods": ["drip", "basin"],
        "discouraged_methods": ["flood", "sprinkler"],
        "kc_by_stage": {"germination": 0.6, "seedling": 0.6, "vegetative": 0.6,
                        "flowering": 0.75, "fruiting": 0.85, "maturation": 0.75,
                        "harvest_ready": 0.6},
        "critical_stages": ["fruiting"],
        "salinity": None,
        "notes": "Withhold water 2-3 months before flowering to induce it; irrigate "
                 "from fruit set to development. Kc from Indian orchard practice.",
    },

    "cabbage": {
        "dry_down_at_maturity": False,
        "display_name": "Cabbage", "water_management": "upland",
        "root_depth_m": 0.65, "p": 0.45, "season_days": 120,
        "preferred_methods": ["drip", "furrow", "sprinkler"],
        "discouraged_methods": ["flood"],
        "kc_by_stage": {"germination": 0.7, "seedling": 0.7, "vegetative": 0.9,
                        "flowering": 1.05, "fruiting": 1.05, "maturation": 0.95,
                        "harvest_ready": 0.95},
        "critical_stages": ["fruiting"],
        "salinity": {"threshold": 1.8, "slope": 9.7},
        "notes": "Head formation is the critical stage; uneven watering splits heads.",
    },
}

# Names callers use for the same crops.
CROP_ALIASES = {
    "paddy": "rice", "corn": "maize", "peanut": "groundnut",
    "cluster bean": "guar", "clusterbean": "guar", "peas": "white peas",
    "pea": "white peas", "coriander (leaves)": "coriander", "dhania": "coriander",
    "carom": "ajwain", "soyabean": "soybean",
}

# Used only when the caller names no crop: a reference crop at full cover.
GENERIC_CROP = {
    "display_name": "Unspecified crop", "water_management": "upland",
    "root_depth_m": DEFAULT_ROOT_DEPTH_M, "p": 0.50, "season_days": None,
    "preferred_methods": ["drip", "furrow"], "discouraged_methods": [],
    "kc_by_stage": {s: 1.0 for s in ("germination", "seedling", "vegetative", "flowering",
                                     "fruiting", "maturation", "harvest_ready")},
    "critical_stages": [], "salinity": None,
    "notes": "No crop given - planned for a reference crop (Kc 1.0).",
}

GROWTH_STAGES = ("germination", "seedling", "vegetative", "flowering", "fruiting",
                 "maturation", "harvest_ready", "panicle_initiation")

# FAO-56 Table 11 generic shares of the season: initial, development,
# mid-season, late. Used to map days-after-sowing onto a named stage.
STAGE_SHARES: Final[tuple] = (0.15, 0.25, 0.40, 0.20)


# =============================================================================
# SOILS
# =============================================================================
# theta_fc / theta_wp: volumetric water content (m3/m3) at field capacity and
# wilting point, FAO-56 Table 19 (midpoints of the texture-class ranges).
# percolation_mm_d is used only by the paddy branch (seepage + percolation
# under standing water); upland drainage happens only above field capacity.
# =============================================================================

SOIL_CONFIG: dict = {
    "sandy": {
        "display_name": "Sandy", "theta_fc": 0.12, "theta_wp": 0.045,
        "percolation_mm_d": 8.0, "irrigation_frequency": "high",
        "preferred_methods": ["drip", "sprinkler"], "discouraged_methods": ["flood", "basin"],
        "notes": "Holds little water - small, frequent irrigations; flood loses most "
                 "water below the roots.",
    },
    "sandy_loam": {
        "display_name": "Sandy Loam", "theta_fc": 0.23, "theta_wp": 0.11,
        "percolation_mm_d": 5.0, "irrigation_frequency": "high",
        "preferred_methods": ["drip", "sprinkler", "furrow"], "discouraged_methods": ["flood"],
        "notes": "Light soil - moderate, frequent irrigations.",
    },
    "loamy": {
        "display_name": "Loam", "theta_fc": 0.25, "theta_wp": 0.12,
        "percolation_mm_d": 3.0, "irrigation_frequency": "medium",
        "preferred_methods": ["drip", "sprinkler", "furrow"], "discouraged_methods": [],
        "notes": "Reference soil - balanced retention and drainage.",
    },
    "silt": {
        "display_name": "Silt / Silty Loam", "theta_fc": 0.32, "theta_wp": 0.17,
        "percolation_mm_d": 2.5, "irrigation_frequency": "medium",
        "preferred_methods": ["drip", "sprinkler", "furrow"], "discouraged_methods": [],
        "notes": "Crusts after heavy irrigation - light tillage or mulch helps.",
    },
    "clay_loam": {
        "display_name": "Clay Loam", "theta_fc": 0.33, "theta_wp": 0.20,
        "percolation_mm_d": 2.0, "irrigation_frequency": "low",
        "preferred_methods": ["drip", "furrow"], "discouraged_methods": [],
        "notes": "Good retention; irrigate less often, deeper.",
    },
    "clay": {
        "display_name": "Clay", "theta_fc": 0.36, "theta_wp": 0.22,
        "percolation_mm_d": 1.0, "irrigation_frequency": "low",
        "preferred_methods": ["drip", "furrow"], "discouraged_methods": ["sprinkler"],
        "notes": "Slow infiltration - waterlogging risk; irrigate less often, deeper.",
    },
    "black_cotton": {
        "display_name": "Black Cotton (Vertisol)", "theta_fc": 0.40, "theta_wp": 0.22,
        "percolation_mm_d": 1.0, "irrigation_frequency": "low",
        "preferred_methods": ["drip", "furrow"], "discouraged_methods": ["flood", "sprinkler"],
        "notes": "Stores a lot of water but cracks when dry and seals when wet - "
                 "irrigate before cracks widen; avoid heavy flooding.",
    },
    "alluvial": {
        "display_name": "Alluvial", "theta_fc": 0.28, "theta_wp": 0.12,
        "percolation_mm_d": 3.0, "irrigation_frequency": "medium",
        "preferred_methods": ["drip", "sprinkler", "furrow", "border"], "discouraged_methods": [],
        "notes": "Productive, well-drained loamy soil.",
    },
    "red_laterite": {
        "display_name": "Red Laterite", "theta_fc": 0.22, "theta_wp": 0.12,
        "percolation_mm_d": 5.0, "irrigation_frequency": "high",
        "preferred_methods": ["drip", "sprinkler"], "discouraged_methods": ["flood"],
        "notes": "Low water holding and fast drainage - frequent light irrigation.",
    },
    "peaty": {
        "display_name": "Peaty", "theta_fc": 0.45, "theta_wp": 0.25,
        "percolation_mm_d": 2.0, "irrigation_frequency": "low",
        "preferred_methods": ["drip"], "discouraged_methods": ["flood"],
        "notes": "High organic matter; drainage usually matters more than irrigation.",
    },
}

# Soil names used elsewhere in FarmXpert (crop-prediction classes, Soil
# Health vocabulary) mapped onto the classes above.
SOIL_ALIASES = {
    "sand": "sandy", "loam": "loamy", "silty loam": "silt", "silty_loam": "silt",
    "silty": "silt", "sandy loam": "sandy_loam", "clay loam": "clay_loam",
    "black cotton": "black_cotton", "black": "black_cotton", "vertisol": "black_cotton",
    "regur": "black_cotton", "red laterite": "red_laterite", "red": "red_laterite",
    "laterite": "red_laterite", "saline-alkaline": "loamy", "saline alkaline": "loamy",
}

DEFAULT_SOIL:  Final[str] = "loamy"
DEFAULT_STAGE: Final[str] = "vegetative"

# Sensor sanity: a volumetric reading this far above field capacity is
# saturated or faulty, not a planning input.
MAX_THETA_ABOVE_FC: Final[float] = 0.20
