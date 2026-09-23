"""
FarmXpert Task Scheduler Agent — Schema Definitions
====================================================
Input  : outputs from FarmXpert specialist agents
         (irrigation, soil_health/fertilizer, weather, crop_selector,
          market_intelligence, pest_disease).
Output : a JSON-serialisable TaskPlan — prioritised, conflict-free,
         time-slotted tasks ready for the operations dashboard.

This module purposely keeps every model dataclass-like and JSON-safe.
The scheduler does NOT touch a database and does NOT call other agents —
the client passes each agent's output as a block of the input payload.
"""

from __future__ import annotations

from datetime import date as date_t, datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


# ─────────────────────────────────────────────────────────────────────────────
# ENUMERATIONS
# ─────────────────────────────────────────────────────────────────────────────

class AgentSource(str, Enum):
    IRRIGATION          = "irrigation_agent"
    SOIL_HEALTH         = "soil_health_agent"
    WEATHER             = "weather_agent"
    CROP_SELECTOR       = "crop_selector_agent"
    MARKET_INTELLIGENCE = "market_intelligence_agent"
    PEST_DISEASE        = "pest_disease_agent"
    GROWTH_STAGE        = "growth_stage_agent"


class TaskCategory(str, Enum):
    IRRIGATION     = "irrigation"
    FERTILIZATION  = "fertilization"
    PEST_CONTROL   = "pest_control"
    SOIL_PREP      = "soil_preparation"
    PLANTING       = "planting"
    HARVESTING     = "harvesting"
    MONITORING     = "monitoring"
    PRUNING        = "pruning"
    WEEDING        = "weeding"
    MARKET_ACTION  = "market_action"
    OTHER          = "other"


class TaskStatus(str, Enum):
    SCHEDULED = "scheduled"
    DELAYED   = "delayed"
    SKIPPED   = "skipped"


class Priority(str, Enum):
    CRITICAL = "critical"
    HIGH     = "high"
    MEDIUM   = "medium"
    LOW      = "low"
    DEFERRED = "deferred"


# ─────────────────────────────────────────────────────────────────────────────
# COMMON SUB-MODELS
# ─────────────────────────────────────────────────────────────────────────────

class Location(BaseModel):
    lat: float = Field(..., ge=-90.0, le=90.0)
    lon: float = Field(..., ge=-180.0, le=180.0)


class FarmIdentity(BaseModel):
    """Identifies the farm/field and provides the planning reference time."""
    farm_id: str = Field(..., min_length=1)
    farm_name: Optional[str] = None
    field_id: str = Field(..., min_length=1)
    location: Optional[Location] = None
    total_area_hectares: Optional[float] = Field(None, ge=0)
    current_crop: Optional[str] = None
    growth_stage: Optional[str] = Field(
        None, description="seedling | vegetative | flowering | fruiting | maturity | harvest_ready"
    )
    days_to_harvest: Optional[int] = Field(
        None, ge=0, description="Days until expected harvest - enforces pre-harvest intervals.")
    in_flower: bool = Field(False, description="Crop is flowering - bee-toxic sprays are refused.")
    soil_type: Optional[str] = None
    timezone: str = "UTC"
    current_timestamp: datetime = Field(..., description="The planning anchor — usually 'now' on the farm.")


class ResourceAvailability(BaseModel):
    """Labor, water, equipment and working window for the planning horizon."""
    labor_units_available: int = Field(2, ge=0)
    water_available_liters: float = Field(0.0, ge=0)
    equipment_available: List[str] = Field(default_factory=list)
    budget_available: Optional[float] = Field(None, ge=0)
    working_hours_start: str = Field("06:00", pattern=r"^\d{2}:\d{2}$")
    working_hours_end:   str = Field("18:00", pattern=r"^\d{2}:\d{2}$")


# ─────────────────────────────────────────────────────────────────────────────
# AGENT INPUT BLOCKS — one per specialist agent
# ─────────────────────────────────────────────────────────────────────────────

# ── 1. Weather Watcher Agent block ──────────────────────────────────────────

class WeatherCurrent(BaseModel):
    temperature_c: float = Field(..., description="Current air temperature in °C")
    humidity_percent: float = Field(..., ge=0, le=100)
    wind_speed_kmh: float = Field(..., ge=0)
    conditions: Optional[str] = Field(None, description="e.g., Clear, Rain, Clouds")
    rainfall_today_mm: float = Field(0.0, ge=0)


class WeatherForecastDay(BaseModel):
    date: date_t
    temp_min_c: float
    temp_max_c: float
    rainfall_mm: float = Field(0.0, ge=0)
    rain_probability_percent: float = Field(0.0, ge=0, le=100)
    wind_speed_kmh: float = Field(0.0, ge=0)
    humidity_percent: Optional[float] = Field(None, ge=0, le=100)
    storm_warning: bool = False
    frost_risk: bool = False
    heat_stress_risk: bool = False
    # Hours judged sprayable by the Weather Watcher (wind, Delta-T, temperature,
    # rainfastness already applied). When present the scheduler trusts these
    # instead of re-deciding sprayability from daily min/max values.
    spray_windows: List[str] = Field(
        default_factory=list,
        description='Sprayable windows as "HH:MM-HH:MM" in farm local time.')


class WeatherAlert(BaseModel):
    type: str = Field(..., description="heatwave | heavy_rainfall | storm | frost | …")
    severity: str = Field("medium", description="low | medium | high | critical")
    message: str
    date: Optional[date_t] = None
    recommendations: List[str] = Field(default_factory=list)


class WeatherAgentData(BaseModel):
    current: Optional[WeatherCurrent] = None
    forecast: List[WeatherForecastDay] = Field(default_factory=list)
    alerts: List[WeatherAlert] = Field(default_factory=list)


# ── 2. Irrigation Planner Agent block ───────────────────────────────────────

class IrrigationDay(BaseModel):
    date: date_t
    irrigation_required: bool
    water_depth_mm: Optional[float] = Field(None, ge=0)
    duration_hours: Optional[float] = Field(None, ge=0)
    water_volume_liters: Optional[float] = Field(None, ge=0, description="Computed volume if known")
    timing: Optional[str] = Field(None, description="morning | afternoon | evening")
    method: str = Field("drip", description="drip | sprinkler | flood")
    reason: Optional[str] = None


class IrrigationAgentData(BaseModel):
    schedule: List[IrrigationDay] = Field(default_factory=list)
    soil_moisture_current_percent: Optional[float] = Field(None, ge=0, le=100)
    water_savings_percent: Optional[float] = Field(None, ge=0, le=100)
    alerts: List[Dict[str, Any]] = Field(default_factory=list)


# ── 3. Soil Health / Fertilizer Agent block ─────────────────────────────────

class FertilizerRecommendation(BaseModel):
    fertilizer: str = Field(..., description="Config key, e.g. urea, dap, ammonium_sulfate")
    display_name: str = Field(..., description="Full product name with grade")
    dosage: str = Field(..., description="e.g. 80-120 kg/ha")
    timing: str = Field(..., description="When/how often to apply")
    method: str = Field(..., description="e.g. soil_application_with_irrigation")
    triggered_by: Optional[str] = Field(None, description="Alert code that triggered this")
    cautions: List[str] = Field(default_factory=list)


class SoilAlert(BaseModel):
    type: str
    message: str
    severity: str = Field("medium", description="info | low | medium | high | critical")


class SoilHealthAgentData(BaseModel):
    soil_health_score: Optional[float] = Field(None, ge=0, le=100)
    soil_health_status: Optional[str] = Field(None, description="Excellent | Good | Fair | Poor | Critical")
    summary: Optional[str] = None
    fertilizers: List[FertilizerRecommendation] = Field(default_factory=list)
    critical_factors: List[str] = Field(default_factory=list)
    alerts: List[SoilAlert] = Field(default_factory=list)


# ── 4. Crop Selector Agent block ────────────────────────────────────────────

class CropRecommendation(BaseModel):
    crop_name: str
    suitability_score: float = Field(..., ge=0, le=10)
    variety: Optional[str] = None
    water_requirement: Optional[str] = None
    duration_days: Optional[int] = Field(None, ge=0)
    expected_yield: Optional[str] = None


class CropSelectorAgentData(BaseModel):
    """Crop planning context. Named for the original crop-selector agent; the
    Crop Prediction agent now fills it through its scheduler adapter."""
    recommended_crops: List[CropRecommendation] = Field(default_factory=list)
    current_growth_stage: Optional[str] = None
    days_since_planting: Optional[int] = Field(None, ge=0)
    days_to_harvest: Optional[int] = Field(None, ge=0)
    planting_window_start: Optional[date_t] = None
    planting_window_end: Optional[date_t] = None


# ── 5. Market Intelligence Agent block ──────────────────────────────────────

class MarketIntelligenceAgentData(BaseModel):
    """
    Market intelligence is now **informational only** — it carries price /
    forecast context for the scheduler's narrative summary but does not
    drive any scheduler task. When `recommended_action` is omitted the
    scheduler emits no market_action task.
    """
    commodity: str
    current_modal_price_per_quintal: Optional[float] = Field(
        None, ge=0, description="Aggregated current modal price across markets",
    )
    predicted_price_per_quintal: Optional[float] = Field(
        None, ge=0, description="Forecast price (LSTM / WMA / fallback)",
    )
    predicted_trend: Optional[str] = Field(
        None, description="increasing | decreasing | stable",
    )
    historical_trend: Optional[str] = Field(
        None, description="increasing | decreasing | stable (OLS over window)",
    )
    confidence: Optional[float] = Field(None, ge=0.0, le=1.0)

    # Optional — kept for back-compat with callers that still pass an action.
    # When None, the scheduler emits no market_action task.
    recommended_action: Optional[str] = Field(
        None, description="(deprecated) SELL_NOW | SELL_IN_OTHER_MANDI | HOLD",
    )
    reason: Optional[str] = None


# ── 6. Pest / Disease Agent block ───────────────────────────────────────────

class PestDiseaseAgentData(BaseModel):
    threat_detected: bool = False
    threat_type: Optional[str] = Field(None, description="aphid | fungal_blight | …")
    severity: float = Field(0.0, ge=0, le=10)
    affected_area_percent: float = Field(0.0, ge=0, le=100)
    treatment_type: Optional[str] = Field(None, description="pesticide | fungicide | biocontrol")
    chemical_name: Optional[str] = None
    application_rate_ml_per_liter: Optional[float] = Field(None, ge=0)
    pre_harvest_interval_days: Optional[int] = Field(
        None, ge=0, description="Days that must pass between this spray and harvest (label PHI).")
    re_entry_interval_hours: Optional[float] = Field(
        None, ge=0, description="Hours before workers may re-enter the treated field (label REI).")
    bee_toxic: bool = Field(
        False, description="Product is toxic to pollinators - never applied to a crop in flower.")
    requires_dry_conditions: bool = True


# ─────────────────────────────────────────────────────────────────────────────
# SCHEDULER INPUT
# ─────────────────────────────────────────────────────────────────────────────

class SchedulerInput(BaseModel):
    """
    Complete input to the Task Scheduler Agent.

    Pass any subset of agent blocks — the scheduler builds tasks from
    whichever blocks are present. At least one agent block is required.
    """
    request_id: str = Field(..., min_length=1)
    farm: FarmIdentity
    resources: ResourceAvailability = Field(default_factory=ResourceAvailability)
    planning_horizon_days: int = Field(3, ge=1, le=14)

    weather_agent:              Optional[WeatherAgentData]              = None
    irrigation_agent:           Optional[IrrigationAgentData]           = None
    soil_health_agent:          Optional[SoilHealthAgentData]           = None
    crop_selector_agent:        Optional[CropSelectorAgentData]         = None
    market_intelligence_agent:  Optional[MarketIntelligenceAgentData]   = None
    pest_disease_agent:         Optional[PestDiseaseAgentData]          = None

    @model_validator(mode="after")
    def _at_least_one_agent_block(self) -> "SchedulerInput":
        if not any([
            self.weather_agent,
            self.irrigation_agent,
            self.soil_health_agent,
            self.crop_selector_agent,
            self.market_intelligence_agent,
            self.pest_disease_agent,
        ]):
            raise ValueError(
                "At least one agent data block must be provided to generate a task plan."
            )
        return self


# ─────────────────────────────────────────────────────────────────────────────
# SCHEDULER OUTPUT
# ─────────────────────────────────────────────────────────────────────────────

class ResourcesRequired(BaseModel):
    labor_units: int = 0
    water_liters: float = 0.0
    equipment: List[str] = Field(default_factory=list)


class ScheduledTask(BaseModel):
    task_id: str
    source_agent: AgentSource
    farm_id: str
    field_id: str

    title: str
    description: str
    category: TaskCategory

    status: TaskStatus
    priority: Priority
    priority_score: float = Field(..., ge=0)

    scheduled_date: Optional[date_t] = None
    scheduled_start_time: Optional[str] = Field(None, description="HH:MM in farm local time")
    scheduled_end_time: Optional[str]   = Field(None, description="HH:MM in farm local time")
    duration_minutes: int = Field(..., ge=1)

    decision: str = Field(..., description="execute_now | delay | skip")
    reason: str
    delay_until_date: Optional[date_t] = None
    skip_reason: Optional[str] = None

    resources_required: ResourcesRequired = Field(default_factory=ResourcesRequired)

    instructions: List[str] = Field(default_factory=list)
    precautions:  List[str] = Field(default_factory=list)
    kpis:         List[str] = Field(default_factory=list)

    weather_constraint_applied:  bool = False
    resource_constraint_applied: bool = False

    # ── Farmer-facing guidance ──────────────────────────────────────────
    why_now: str = Field("", description="Why this job matters on this day, in one line.")
    do:      List[str] = Field(default_factory=list, description="What to do.")
    do_not:  List[str] = Field(default_factory=list, description="What not to do, and why.")
    safety:  List[str] = Field(default_factory=list, description="Protecting the person doing the work.")
    cost_of_delay: Optional[str] = Field(
        None, description="What waiting costs - stated whenever a task is delayed.")
    blocked_by: List[str] = Field(
        default_factory=list, description="Plain-language reasons this could not be done sooner.")

    metadata: Dict[str, Any] = Field(default_factory=dict)


class RefusedTask(BaseModel):
    """A job the scheduler will not place at all, and the rule that forbids it.

    Refusals are food-safety and human-safety rules (pre-harvest interval,
    bee-toxic spray on a flowering crop). Unlike a delay, a refusal is never
    rescheduled automatically - the farmer must change the plan or the product.
    """
    title: str
    category: TaskCategory
    rule: str
    explanation: str
    what_to_do_instead: Optional[str] = None


class ConflictRecord(BaseModel):
    conflict_id: str
    conflicting_task_ids: List[str]
    conflict_type: str
    description: str
    resolution: str = Field(..., description="reschedule | skip | merge | override")
    resolution_reason: str


class DailyPlan(BaseModel):
    plan_date: date_t
    weather_note: Optional[str] = None
    tasks: List[ScheduledTask]
    total_tasks: int
    critical_tasks: int
    total_labor_units: int
    total_water_liters: float
    estimated_total_duration_minutes: int
    notes: List[str] = Field(default_factory=list)


class TaskPlan(BaseModel):
    plan_id: str
    request_id: str
    farm_id: str
    field_id: str
    generated_at: datetime
    planning_horizon_days: int

    summary: str
    headline: str = Field("", description="One line for the top of the farmer's day.")
    do_first: Optional[str] = Field(None, description="Title of the single most important task today.")
    total_tasks_scheduled: int
    total_tasks_delayed: int
    total_tasks_skipped: int

    daily_plans: List[DailyPlan]
    all_tasks: List[ScheduledTask]
    critical_tasks: List[ScheduledTask]
    conflicts_detected: List[ConflictRecord]
    refused_tasks: List[RefusedTask] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)

    agent_version: str = "3.0.0"

    model_config = ConfigDict(json_encoders={datetime: lambda v: v.isoformat()})


# ─────────────────────────────────────────────────────────────────────────────
# API WRAPPERS
# ─────────────────────────────────────────────────────────────────────────────

class ScheduleResponse(BaseModel):
    success: bool
    request_id: str
    plan: Optional[TaskPlan] = None
    error: Optional[str] = None
    processing_time_ms: float = 0.0
