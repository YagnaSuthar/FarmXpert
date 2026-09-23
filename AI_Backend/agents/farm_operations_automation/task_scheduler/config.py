"""
Task Scheduler Agent — Configuration
=====================================
What each kind of farm task needs, what stops it, and how the day is packed.

Operational settings (horizon, day capacity) can be overridden per
deployment with FARMXPERT_TS_* environment variables. The agronomic and
safety rules below cannot: a pre-harvest interval or a spray wind limit
means the same thing on every farm, and loosening one puts either the
crop, the farmer, or the person eating the produce at risk.

Sources are named next to each rule.
"""

from __future__ import annotations

import os
from typing import Dict, Final


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

AGENT_ID:      Final[str] = "task_scheduler_agent"
AGENT_VERSION: Final[str] = "3.0.0"
AGENT_NAME:    Final[str] = "Task Scheduler"


# ── Planning horizon and day capacity ───────────────────────────────────────

DEFAULT_HORIZON_DAYS: Final[int] = _env_int("FARMXPERT_TS_HORIZON", 3)
MAX_HORIZON_DAYS:     Final[int] = _env_int("FARMXPERT_TS_MAX_HORIZON", 14)

# A day with more than this many jobs is a list nobody finishes. The limit is
# on the farmer's attention, not on the field.
MAX_TASKS_PER_DAY:      Final[int]   = _env_int("FARMXPERT_TS_MAX_TASKS", 8)
MAX_WORK_HOURS_PER_DAY: Final[float] = _env_float("FARMXPERT_TS_MAX_HOURS", 10.0)

DEFAULT_WORK_START: Final[str] = os.getenv("FARMXPERT_TS_WORK_START", "06:00")
DEFAULT_WORK_END:   Final[str] = os.getenv("FARMXPERT_TS_WORK_END", "18:00")

# Slots are rounded to this many minutes so the plan reads like a human wrote
# it ("07:30", not "07:23").
SLOT_GRANULARITY_MIN: Final[int] = 15


# ── Priority ────────────────────────────────────────────────────────────────
#
# priority_score = urgency*W_URGENCY + risk*W_RISK + impact*W_IMPACT, on 0-10.
#   urgency - how soon the window closes
#   risk    - what is lost if it is not done
#   impact  - how much the season gains if it is done well

WEIGHT_URGENCY: Final[float] = 0.40
WEIGHT_RISK:    Final[float] = 0.35
WEIGHT_IMPACT:  Final[float] = 0.25

PRIORITY_BANDS: Final[tuple] = (
    ("critical", 8.0),
    ("high",     6.0),
    ("medium",   4.0),
    ("low",      2.0),
)
# Below the last band a task is "deferred": worth doing, not worth a slot now.

# Weather is measured, not inferred, so it outranks a model's opinion; a pest
# outbreak doubles every few days, so it outranks a routine recommendation.
SOURCE_TRUST: Final[Dict[str, float]] = {
    "weather_agent":             1.20,
    "pest_disease_agent":        1.10,
    "irrigation_agent":          1.00,
    "soil_health_agent":         1.00,
    "growth_stage_agent":        1.00,
    "crop_selector_agent":       0.90,
    "market_intelligence_agent": 0.90,
}


# ── Task categories ─────────────────────────────────────────────────────────
#
# One entry per kind of work. `duration_min`, `labor`, `equipment` are the
# defaults used when the source agent does not say; the flags drive which
# weather rules apply.
#
#   dry_hours_after  - hours the crop must stay dry after the job for it to
#                      work at all (rainfastness / absorption).
#   spray            - it is applied through a nozzle, so wind, Delta-T and
#                      temperature limits apply (GRDC spray application manual).
#   heat_sensitive   - people are working hard in the open; heat is a safety
#                      limit, not a preference.
#   daylight_only    - cannot be done safely or accurately after dark.

CATEGORY_CONFIG: Final[Dict[str, dict]] = {
    "irrigation": {
        "display_name": "Irrigation",
        "duration_min": 90, "labor": 1, "equipment": ["irrigation_set"],
        "preferred_timing": "morning",
        "dry_hours_after": 0, "spray": False,
        "heat_sensitive": False, "daylight_only": False,
        "why": "Water at the right time decides yield more than any other single job.",
    },
    "fertilization": {
        "display_name": "Fertilizer application",
        "duration_min": 60, "labor": 1, "equipment": ["spreader"],
        "preferred_timing": "morning",
        # Urea on a wet-then-rained field is lost to leaching and
        # volatilisation; FAO and ICAR extension both advise a dry spell
        # around application, then a light irrigation to move it in.
        "dry_hours_after": 6, "spray": False,
        "heat_sensitive": False, "daylight_only": True,
        "why": "Nutrients applied at the wrong moment wash away and cost money twice.",
    },
    "pest_control": {
        "display_name": "Pest / disease control",
        "duration_min": 60, "labor": 2, "equipment": ["sprayer"],
        "preferred_timing": "morning",
        # Rainfastness: most foliar products need ~4 rain-free hours.
        "dry_hours_after": 4, "spray": True,
        "heat_sensitive": True, "daylight_only": True,
        "why": "A pest population doubles in days - a late spray costs several times more.",
    },
    "soil_preparation": {
        "display_name": "Land preparation",
        "duration_min": 150, "labor": 2, "equipment": ["tractor"],
        "preferred_timing": "morning",
        "dry_hours_after": 0, "spray": False,
        "heat_sensitive": True, "daylight_only": True,
        "why": "Tilth set now cannot be corrected after sowing.",
    },
    "planting": {
        "display_name": "Sowing / planting",
        "duration_min": 120, "labor": 2, "equipment": ["seed_drill"],
        "preferred_timing": "morning",
        "dry_hours_after": 0, "spray": False,
        "heat_sensitive": True, "daylight_only": True,
        "why": "The sowing date fixes the whole season's calendar.",
    },
    "harvesting": {
        "display_name": "Harvest",
        "duration_min": 240, "labor": 4, "equipment": ["harvester"],
        "preferred_timing": "morning",
        "dry_hours_after": 0, "spray": False,
        "heat_sensitive": True, "daylight_only": True,
        "why": "Grain harvested wet or late loses both weight and grade.",
    },
    "monitoring": {
        "display_name": "Field inspection",
        "duration_min": 30, "labor": 1, "equipment": [],
        "preferred_timing": "morning",
        "dry_hours_after": 0, "spray": False,
        "heat_sensitive": False, "daylight_only": True,
        "why": "Problems caught while small are cheap; the walk itself costs nothing.",
    },
    "pruning": {
        "display_name": "Pruning / training",
        "duration_min": 120, "labor": 2, "equipment": ["secateurs"],
        "preferred_timing": "morning",
        "dry_hours_after": 0, "spray": False,
        "heat_sensitive": True, "daylight_only": True,
        "why": "Open cuts in wet weather invite canker and gummosis.",
    },
    "weeding": {
        "display_name": "Weeding",
        "duration_min": 180, "labor": 3, "equipment": [],
        "preferred_timing": "morning",
        "dry_hours_after": 0, "spray": False,
        "heat_sensitive": True, "daylight_only": True,
        "why": "Weeds take water and nitrogen the crop paid for.",
    },
    "market_action": {
        "display_name": "Market",
        "duration_min": 180, "labor": 1, "equipment": [],
        "preferred_timing": "morning",
        "dry_hours_after": 0, "spray": False,
        "heat_sensitive": False, "daylight_only": True,
        "why": "Price windows close faster than field windows.",
    },
    "other": {
        "display_name": "Farm work",
        "duration_min": 60, "labor": 1, "equipment": [],
        "preferred_timing": "morning",
        "dry_hours_after": 0, "spray": False,
        "heat_sensitive": False, "daylight_only": True,
        "why": "",
    },
}


# ── Weather limits ──────────────────────────────────────────────────────────
#
# These mirror the Weather Watcher's own thresholds so the two agents never
# tell a farmer different things about the same day.

# Spraying (GRDC; IMD wind categories). Wind is the drift limit; the
# temperature band is where the droplet still reaches the leaf and is taken up.
SPRAY_WIND_MAX_KMH:  Final[float] = 15.0
SPRAY_TEMP_MAX_C:    Final[float] = 30.0
SPRAY_TEMP_MIN_C:    Final[float] = 5.0

# Rain that actually interferes, in mm - not probability. A 70 % chance of
# 1 mm stops nothing; 15 mm stops a spray and replaces an irrigation.
RAIN_WETS_CANOPY_MM: Final[float] = 2.0    # enough to wash off a fresh spray
RAIN_BLOCKS_FIELD_MM: Final[float] = 10.0  # ground too wet for machinery
RAIN_LEACHES_FERT_MM: Final[float] = 25.0  # heavy enough to move nitrate below the root zone

# A forecast day counts as "rain expected" only when both the amount and the
# confidence are meaningful.
RAIN_PROBABILITY_MIN: Final[float] = 50.0

# Irrigation is only cancelled when the rain covers at least this share of the
# planned depth. Otherwise the irrigation is reduced, not dropped.
RAIN_COVERS_IRRIGATION: Final[float] = 0.80

# People. NOAA heat index "danger" band; IMD heat-wave criterion.
HEAT_STRESS_TEMP_C:    Final[float] = 38.0
HEAT_DANGER_TEMP_C:    Final[float] = 42.0
# Below this daytime maximum the ground stays frozen (same value the
# irrigation and weather agents use).
FROZEN_GROUND_TMAX_C:  Final[float] = 2.0
FROST_TMIN_C:          Final[float] = 2.0

# Categories frost puts at risk (young tissue, exposed roots, standing water).
FROST_BLOCKS: Final[frozenset] = frozenset({"planting", "irrigation", "fertilization", "pruning"})

# Wind that makes any open-field work unsafe (Beaufort 8, gale).
GALE_WIND_KMH: Final[float] = 62.0


# ── Ordering between jobs ───────────────────────────────────────────────────
#
# Hours that must pass between one job and the next on the same field.
# Key is "earlier->later".

DEPENDENCY_GAP_HOURS: Final[Dict[str, float]] = {
    # Dry fertilizer must be watered in, but not immediately - give the
    # granule time to sit before the water moves it.
    "fertilization->irrigation":  6.0,
    # Do not fertilise onto a saturated surface: it runs off.
    "irrigation->fertilization":  12.0,
    # Spray deposits must dry before water touches them.
    "pest_control->irrigation":   24.0,
    # A wet canopy dilutes a spray and a wet soil compacts under the sprayer.
    "irrigation->pest_control":   12.0,
    # Let a tilled seedbed settle so seed depth stays true.
    "soil_preparation->planting": 24.0,
    # Germination water, as soon as practical.
    "planting->irrigation":       2.0,
    # Pruning wounds should be protected before overhead water.
    "pruning->irrigation":        24.0,
}


# ── Food safety ─────────────────────────────────────────────────────────────
#
# Pre-harvest interval (PHI): days between the last spray and harvest, set on
# every pesticide label and enforced by FSSAI residue limits. Re-entry
# interval (REI): hours before people may work in the treated field again.
# The scheduler will never place a spray that breaks a PHI - it is the one
# rule it refuses rather than delays.

DEFAULT_PHI_DAYS: Final[int] = 7
DEFAULT_REI_HOURS: Final[float] = 12.0

# Farmer-facing: a spray this close to harvest is refused outright.
PHI_HARD_BLOCK: Final[bool] = True


# ── Delay handling ──────────────────────────────────────────────────────────
#
# A delayed task is not a free action. Each category loses value per day of
# delay, as a fraction of its impact - used to warn the farmer and to escalate
# a task that has been pushed too often.

DELAY_COST_PER_DAY: Final[Dict[str, float]] = {
    "pest_control":     0.25,   # population growth; the classic doubling curve
    "irrigation":       0.20,   # depletion continues, yield loss at flowering
    "harvesting":       0.15,   # shattering, grade loss, weather exposure
    "fertilization":    0.08,
    "planting":         0.10,   # each late day shortens the season
    "weeding":          0.06,
    "soil_preparation": 0.04,
    "pruning":          0.03,
    "monitoring":       0.02,
    "market_action":    0.10,
    "other":            0.02,
}

# Once a task has lost this share of its value to delay, it is escalated in
# the plan rather than quietly pushed again.
DELAY_ESCALATE_AT: Final[float] = 0.30

# A recommendation older than this is stale - the field has moved on.
INPUT_STALE_HOURS: Final[float] = 36.0
