# config.py
"""
FarmXpert Task Scheduler Agent — Configuration
===============================================
All tunable parameters, thresholds, weights, and environment config.
Override via environment variables or a .env file for deployment.
"""

from __future__ import annotations

import os
from typing import Dict
from pydantic import Field
from pydantic_settings import BaseSettings


class SchedulerConfig(BaseSettings):
    """
    Central configuration class. All values can be overridden via environment
    variables (prefixed with FARMXPERT_).
    """

    # ── Application Identity ─────────────────────────────────────────────────
    APP_NAME: str = "FarmXpert Task Scheduler Agent"
    APP_VERSION: str = "1.0.0"
    ENVIRONMENT: str = Field("production", description="production | staging | development")
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"

    # ── API Server ───────────────────────────────────────────────────────────
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8080
    API_WORKERS: int = 4
    API_TIMEOUT_SECONDS: int = 30
    CORS_ORIGINS: list[str] = ["*"]

    # ── Scheduling Horizons ──────────────────────────────────────────────────
    DEFAULT_PLANNING_HORIZON_DAYS: int = 3
    MAX_PLANNING_HORIZON_DAYS: int = 7
    CRON_SCHEDULE_HOUR: int = 5       # 5 AM daily cron
    CRON_SCHEDULE_MINUTE: int = 30

    # ── Priority Scoring Weights ─────────────────────────────────────────────
    # priority_score = (urgency * W_URGENCY) + (risk * W_RISK) + (impact * W_IMPACT)
    PRIORITY_WEIGHT_URGENCY: float = 0.40
    PRIORITY_WEIGHT_RISK: float = 0.35
    PRIORITY_WEIGHT_IMPACT: float = 0.25

    # Score thresholds → Priority levels
    PRIORITY_CRITICAL_THRESHOLD: float = 8.0   # score >= 8.0 → CRITICAL
    PRIORITY_HIGH_THRESHOLD: float = 6.0       # score >= 6.0 → HIGH
    PRIORITY_MEDIUM_THRESHOLD: float = 4.0     # score >= 4.0 → MEDIUM
    PRIORITY_LOW_THRESHOLD: float = 2.0        # score >= 2.0 → LOW
    # Below LOW_THRESHOLD → DEFERRED

    # ── Weather Constraint Thresholds ────────────────────────────────────────
    # Rain probability above this % → delay irrigation & pesticide
    RAIN_PROBABILITY_DELAY_THRESHOLD: float = 70.0

    # Rain probability above this % → delay any outdoor sensitive task
    RAIN_PROBABILITY_SENSITIVE_THRESHOLD: float = 85.0

    # Wind speed above this km/h → delay pesticide/fertilizer application
    WIND_SPEED_SPRAY_MAX_KMH: float = 15.0

    # Temperature limits for chemical applications
    TEMP_SPRAY_MIN_C: float = 5.0
    TEMP_SPRAY_MAX_C: float = 35.0

    # Heat stress threshold (°C) — delay labor-intensive tasks
    HEAT_STRESS_TEMP_C: float = 38.0

    # Frost risk → delay sensitive operations (transplanting, etc.)
    FROST_DELAY_CATEGORIES: list[str] = ["planting", "irrigation", "fertilization"]

    # ── Resource Constraints ─────────────────────────────────────────────────
    MIN_LABOR_UNITS_FOR_CRITICAL: int = 1
    WATER_RESERVE_BUFFER_PERCENT: float = 10.0  # Keep 10% water in reserve

    # ── Task Dependencies ────────────────────────────────────────────────────
    # Minimum hours that must pass between these task category pairs
    TASK_DEPENDENCY_GAP_HOURS: Dict[str, int] = {
        "irrigation->fertilization": 2,     # irrigate before fertilizing
        "fertilization->irrigation": 12,    # let fertilizer absorb
        "pest_control->irrigation": 6,      # let pesticide dry
        "irrigation->pest_control": 4,      # soil shouldn't be too wet
        "soil_preparation->planting": 24,   # let soil settle
        "planting->irrigation": 1,          # water immediately after planting
    }

    # ── Conflict Resolution ───────────────────────────────────────────────────
    # Max tasks allowed on a single day before overflow to next day
    MAX_TASKS_PER_DAY: int = 8
    MAX_LABOR_HOURS_PER_DAY: float = 10.0

    # If two tasks from same category in same window → merge or skip duplicate
    ALLOW_SAME_CATEGORY_SAME_DAY: bool = False

    # ── Task Staleness ────────────────────────────────────────────────────────
    # Recommendation older than this many hours is considered stale
    RECOMMENDATION_STALE_HOURS: int = 24

    # ── Retry & Resilience ────────────────────────────────────────────────────
    MAX_SCHEDULING_RETRIES: int = 3
    RETRY_BACKOFF_SECONDS: int = 2

    # ── Observability ────────────────────────────────────────────────────────
    ENABLE_METRICS: bool = True
    METRICS_PORT: int = 9090
    TRACE_SAMPLING_RATE: float = 0.1
    SENTRY_DSN: str = ""

    # ── Storage / Persistence ────────────────────────────────────────────────
    DATABASE_URL: str = Field(
        "sqlite:///./farmxpert_scheduler.db",
        description="SQLAlchemy-compatible DB URL"
    )
    REDIS_URL: str = Field(
        "redis://localhost:6379/0",
        description="Redis for caching and pub/sub"
    )
    ENABLE_PERSISTENCE: bool = False  # Set True in production with DB

    # ── Agent Source Trust Levels ─────────────────────────────────────────────
    # Multiplier applied to scores from each source agent (0.5–1.5)
    AGENT_TRUST_MULTIPLIERS: Dict[str, float] = {
        "irrigation_agent": 1.0,
        "soil_health_agent": 1.0,
        "pest_disease_agent": 1.1,   # Slightly elevated — pest damage is rapid
        "weather_agent": 1.2,        # Weather is ground truth
        "crop_selector_agent": 0.9,
        "growth_stage_agent": 1.0,
    }

    # ── Working Window Defaults ───────────────────────────────────────────────
    DEFAULT_WORK_START_HOUR: int = 6
    DEFAULT_WORK_END_HOUR: int = 18

    # ── Instructions Templates ────────────────────────────────────────────────
    # Used to enrich scheduled task instructions
    ENABLE_INSTRUCTION_ENRICHMENT: bool = True

    class Config:
        env_prefix = "FARMXPERT_"
        case_sensitive = False
        env_file = ".env"
        env_file_encoding = "utf-8"


# Singleton config instance
settings = SchedulerConfig()


# ── Derived Constants (not overridable via env) ───────────────────────────────

# Maps category pair strings → their dependency gap hours
DEPENDENCY_GAPS: Dict[str, int] = settings.TASK_DEPENDENCY_GAP_HOURS

# Human-readable priority thresholds for logging
PRIORITY_BAND_LABELS = {
    "CRITICAL": f"score >= {settings.PRIORITY_CRITICAL_THRESHOLD}",
    "HIGH":     f"score >= {settings.PRIORITY_HIGH_THRESHOLD}",
    "MEDIUM":   f"score >= {settings.PRIORITY_MEDIUM_THRESHOLD}",
    "LOW":      f"score >= {settings.PRIORITY_LOW_THRESHOLD}",
    "DEFERRED": f"score < {settings.PRIORITY_LOW_THRESHOLD}",
}

# Instruction templates per task category
TASK_INSTRUCTIONS: Dict[str, list[str]] = {
    "irrigation": [
        "Verify soil moisture sensors before starting irrigation.",
        "Set flow rate as specified and monitor for leaks.",
        "Record actual water volume delivered post-irrigation.",
        "Check for runoff or pooling and adjust application rate.",
    ],
    "fertilization": [
        "Confirm soil moisture is adequate before applying fertilizer.",
        "Calibrate spreader/injector to recommended rate.",
        "Apply evenly across the designated field zone.",
        "Log batch number, product name, and quantity applied.",
        "Do not apply if rain is expected within 4 hours.",
    ],
    "pest_control": [
        "Wear full PPE: gloves, goggles, respirator.",
        "Calibrate sprayer nozzle pressure before use.",
        "Apply during early morning or evening — avoid heat of day.",
        "Observe re-entry interval before allowing workers back.",
        "Log chemical lot number and application date.",
        "Dispose of empty containers per local regulations.",
    ],
    "soil_preparation": [
        "Check soil moisture — do not till wet soil.",
        "Set tillage depth as specified.",
        "Remove crop residue if required by protocol.",
        "Record field conditions and equipment settings.",
    ],
    "planting": [
        "Verify seed lot quality and germination rate.",
        "Set planting depth and row spacing per crop specification.",
        "Ensure soil temperature is within optimal range.",
        "Record planting density and GPS waypoints.",
    ],
    "monitoring": [
        "Use calibrated sensors or visual inspection protocol.",
        "Record observations in the field log.",
        "Photograph affected areas if disease or pest signs are present.",
        "Report anomalies to farm manager immediately.",
    ],
    "harvesting": [
        "Inspect crop maturity indicators before starting.",
        "Set harvest equipment to correct settings.",
        "Track field yield per zone.",
        "Minimize mechanical damage to produce.",
    ],
    "pruning": [
        "Use sterilized cutting tools.",
        "Follow crop-specific pruning protocol.",
        "Remove and dispose of pruned material properly.",
    ],
    "weeding": [
        "Identify weed species before treatment.",
        "Use appropriate mechanical or chemical method.",
        "Avoid disturbing crop root zone.",
    ],
    "other": [
        "Follow farm SOPs for this activity.",
        "Document start time, end time, and outcome.",
    ],
}

# KPI templates per task category
TASK_KPIS: Dict[str, list[str]] = {
    "irrigation":    ["Soil moisture reaches target FC fraction", "No runoff detected", "Water usage within ±5% of plan"],
    "fertilization": ["Uniform application confirmed", "Post-application soil NPK within target range"],
    "pest_control":  ["Pest severity score reduced by ≥50% within 5 days", "No crop damage spread"],
    "planting":      ["≥85% germination rate within 7 days", "Even emergence across field"],
    "monitoring":    ["All sensor readings logged", "Report submitted within 1 hour"],
    "harvesting":    ["Yield variance <5% from forecast", "Post-harvest loss <2%"],
    "soil_preparation": ["Seedbed tilth meets specification", "Bulk density within target range"],
    "pruning":       ["Target canopy coverage achieved"],
    "weeding":       ["Weed coverage reduced to <5% of field area"],
    "other":         ["Task completion confirmed and logged"],
}