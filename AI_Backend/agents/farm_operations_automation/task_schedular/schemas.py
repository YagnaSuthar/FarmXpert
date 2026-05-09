"""
FarmXpert Task Scheduler Agent — Schema Definitions
====================================================
Pydantic v2 models for all agent inputs, outputs, and internal data structures.
These schemas enforce strict data contracts between specialist agents and the scheduler.
"""

from __future__ import annotations

from datetime import datetime, date
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator, model_validator


# ─────────────────────────────────────────────────────────────────────────────
# ENUMERATIONS
# ─────────────────────────────────────────────────────────────────────────────

class AgentSource(str, Enum):
    IRRIGATION       = "irrigation_agent"
    SOIL_HEALTH      = "soil_health_agent"
    PEST_DISEASE     = "pest_disease_agent"
    WEATHER          = "weather_agent"
    CROP_SELECTOR    = "crop_selector_agent"
    GROWTH_STAGE     = "growth_stage_agent"


class TaskStatus(str, Enum):
    PENDING    = "pending"
    SCHEDULED  = "scheduled"
    DELAYED    = "delayed"
    SKIPPED    = "skipped"
    COMPLETED  = "completed"
    CANCELLED  = "cancelled"


class TaskCategory(str, Enum):
    IRRIGATION    = "irrigation"
    FERTILIZATION = "fertilization"
    PEST_CONTROL  = "pest_control"
    HARVESTING    = "harvesting"
    PLANTING      = "planting"
    SOIL_PREP     = "soil_preparation"
    MONITORING    = "monitoring"
    PRUNING       = "pruning"
    WEEDING       = "weeding"
    OTHER         = "other"


class Priority(str, Enum):
    CRITICAL  = "critical"   # Execute immediately — yield/crop at risk
    HIGH      = "high"       # Execute today
    MEDIUM    = "medium"     # Execute within 2–3 days
    LOW       = "low"        # Execute this week
    DEFERRED  = "deferred"   # Reschedule when conditions allow


class ConflictResolution(str, Enum):
    DELAY        = "delay"
    SKIP         = "skip"
    MERGE        = "merge"
    RESCHEDULE   = "reschedule"
    OVERRIDE     = "override"


class SoilMoistureLevel(str, Enum):
    DRY          = "dry"
    OPTIMAL      = "optimal"
    WET          = "wet"
    WATERLOGGED  = "waterlogged"


class GrowthStage(str, Enum):
    GERMINATION   = "germination"
    SEEDLING      = "seedling"
    VEGETATIVE    = "vegetative"
    FLOWERING     = "flowering"
    FRUITING      = "fruiting"
    MATURATION    = "maturation"
    HARVEST_READY = "harvest_ready"
    DORMANT       = "dormant"


# ─────────────────────────────────────────────────────────────────────────────
# SUB-MODELS: SPECIALIST AGENT RECOMMENDATION PAYLOADS
# ─────────────────────────────────────────────────────────────────────────────

class IrrigationPayload(BaseModel):
    water_volume_liters: float = Field(..., ge=0, description="Recommended irrigation volume in liters")
    duration_minutes: int = Field(..., ge=1, le=720)
    method: str = Field(..., description="e.g., drip, sprinkler, flood")
    soil_moisture_current: SoilMoistureLevel
    target_moisture_level: float = Field(..., ge=0.0, le=1.0, description="0–1 fraction of field capacity")
    deficit_mm: float = Field(..., ge=0.0, description="Soil water deficit in mm")


class SoilHealthPayload(BaseModel):
    ph_current: float = Field(..., ge=0.0, le=14.0)
    ph_target: float = Field(..., ge=0.0, le=14.0)
    nitrogen_ppm: float = Field(..., ge=0)
    phosphorus_ppm: float = Field(..., ge=0)
    potassium_ppm: float = Field(..., ge=0)
    organic_matter_percent: float = Field(..., ge=0.0, le=100.0)
    amendment_type: Optional[str] = None
    amendment_kg_per_hectare: Optional[float] = Field(None, ge=0)
    fertilizer_type: Optional[str] = None
    fertilizer_kg_per_hectare: Optional[float] = Field(None, ge=0)
    application_notes: Optional[str] = None


class PestDiseasePayload(BaseModel):
    threat_type: str = Field(..., description="e.g., aphid, fungal_blight, rootworm")
    severity: float = Field(..., ge=0.0, le=10.0, description="0=none, 10=critical infestation")
    affected_area_percent: float = Field(..., ge=0.0, le=100.0)
    treatment_type: str = Field(..., description="e.g., pesticide, fungicide, biocontrol")
    chemical_name: Optional[str] = None
    application_rate_ml_per_liter: Optional[float] = Field(None, ge=0)
    pre_harvest_interval_days: Optional[int] = Field(None, ge=0)
    re_entry_interval_hours: Optional[int] = Field(None, ge=0)
    requires_dry_conditions: bool = True


class WeatherPayload(BaseModel):
    forecast_date: date
    temperature_high_c: float
    temperature_low_c: float
    rainfall_mm: float = Field(..., ge=0)
    rain_probability_percent: float = Field(..., ge=0.0, le=100.0)
    wind_speed_kmh: float = Field(..., ge=0)
    humidity_percent: float = Field(..., ge=0.0, le=100.0)
    frost_risk: bool = False
    heat_stress_risk: bool = False
    storm_warning: bool = False
    evapotranspiration_mm: float = Field(..., ge=0, description="ETo in mm/day")


class CropSelectorPayload(BaseModel):
    crop_name: str
    variety: Optional[str] = None
    field_id: str
    planting_date: Optional[date] = None
    expected_harvest_date: Optional[date] = None
    current_growth_stage: GrowthStage
    days_since_planting: int = Field(..., ge=0)
    days_to_harvest: Optional[int] = Field(None, ge=0)


class GrowthStagePayload(BaseModel):
    current_stage: GrowthStage
    stage_progress_percent: float = Field(..., ge=0.0, le=100.0)
    critical_window: bool = Field(False, description="True if in a yield-critical period (e.g., flowering)")
    gdd_accumulated: float = Field(..., ge=0, description="Growing Degree Days accumulated")
    gdd_to_next_stage: float = Field(..., ge=0)
    nutrient_demand: str = Field(..., description="e.g., high_nitrogen, balanced, low_input")
    water_sensitivity: str = Field(..., description="e.g., drought_tolerant, water_sensitive")


# ─────────────────────────────────────────────────────────────────────────────
# AGENT RECOMMENDATION (UNIFIED INPUT MODEL)
# ─────────────────────────────────────────────────────────────────────────────

class AgentRecommendation(BaseModel):
    """Single recommendation from any specialist agent."""
    recommendation_id: str = Field(..., description="Unique ID from source agent")
    source_agent: AgentSource
    farm_id: str
    field_id: str
    generated_at: datetime
    valid_until: Optional[datetime] = None

    task_category: TaskCategory
    title: str = Field(..., max_length=120)
    description: str = Field(..., max_length=1000)

    urgency_score: float = Field(..., ge=0.0, le=10.0)
    risk_score: float = Field(..., ge=0.0, le=10.0)
    impact_score: float = Field(..., ge=0.0, le=10.0)

    earliest_start: Optional[datetime] = None
    latest_start: Optional[datetime] = None
    estimated_duration_minutes: int = Field(..., ge=1)
    requires_dry_weather: bool = False
    requires_labor: bool = True
    labor_units_required: int = Field(1, ge=0)
    equipment_required: List[str] = Field(default_factory=list)
    depends_on: List[str] = Field(default_factory=list, description="List of recommendation_ids this task depends on")

    # Specialist payload (only one should be set per recommendation)
    irrigation_payload: Optional[IrrigationPayload] = None
    soil_health_payload: Optional[SoilHealthPayload] = None
    pest_disease_payload: Optional[PestDiseasePayload] = None
    weather_payload: Optional[WeatherPayload] = None
    crop_selector_payload: Optional[CropSelectorPayload] = None
    growth_stage_payload: Optional[GrowthStagePayload] = None

    metadata: Dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_scores(self) -> "AgentRecommendation":
        total = self.urgency_score + self.risk_score + self.impact_score
        if total == 0:
            raise ValueError("At least one of urgency/risk/impact scores must be > 0")
        return self


# ─────────────────────────────────────────────────────────────────────────────
# RESOURCE & ENVIRONMENT CONTEXT
# ─────────────────────────────────────────────────────────────────────────────

class ResourceAvailability(BaseModel):
    labor_available: bool = True
    labor_units_available: int = Field(2, ge=0)
    water_available_liters: float = Field(..., ge=0)
    equipment_available: List[str] = Field(default_factory=list)
    budget_available: Optional[float] = Field(None, ge=0)
    working_hours_start: str = Field("06:00", pattern=r"^\d{2}:\d{2}$")
    working_hours_end: str = Field("18:00", pattern=r"^\d{2}:\d{2}$")

    @field_validator("labor_units_available")
    @classmethod
    def labor_units_require_available(cls, v: int, info: Any) -> int:
        return v


class FarmContext(BaseModel):
    farm_id: str
    farm_name: str
    field_ids: List[str]
    total_area_hectares: float = Field(..., ge=0)
    timezone: str = Field("UTC")
    current_timestamp: datetime
    weather_forecast: List[WeatherPayload] = Field(..., min_length=1, max_length=7)
    resources: ResourceAvailability
    active_crop: Optional[str] = None
    growth_stage: Optional[GrowthStage] = None


# ─────────────────────────────────────────────────────────────────────────────
# SCHEDULER INPUT & OUTPUT
# ─────────────────────────────────────────────────────────────────────────────

class SchedulerInput(BaseModel):
    """Complete input payload to the Task Scheduler Agent."""
    request_id: str
    farm_context: FarmContext
    recommendations: List[AgentRecommendation] = Field(..., min_length=1)
    planning_horizon_days: int = Field(3, ge=1, le=7, description="Days ahead to schedule")
    force_reschedule: bool = False
    dry_run: bool = Field(False, description="If True, compute plan without persisting")


class ConflictRecord(BaseModel):
    """Documents a detected conflict and how it was resolved."""
    conflict_id: str
    conflicting_recommendation_ids: List[str]
    conflict_type: str
    description: str
    resolution: ConflictResolution
    resolution_reason: str


class ScheduledTask(BaseModel):
    """A fully resolved, scheduled task — output unit of the scheduler."""
    task_id: str
    source_recommendation_id: str
    source_agent: AgentSource
    farm_id: str
    field_id: str

    title: str
    description: str
    category: TaskCategory
    status: TaskStatus
    priority: Priority
    priority_score: float = Field(..., ge=0.0, description="Computed composite score")

    scheduled_start: Optional[datetime] = None
    scheduled_end: Optional[datetime] = None
    estimated_duration_minutes: int

    assigned_labor_units: int
    equipment_assigned: List[str]

    decision: str = Field(..., description="execute_now | delay | skip")
    reason: str = Field(..., description="Human-readable scheduling rationale")
    delay_until: Optional[datetime] = None
    skip_reason: Optional[str] = None

    weather_constraint_applied: bool = False
    dependency_constraint_applied: bool = False
    resource_constraint_applied: bool = False

    instructions: List[str] = Field(default_factory=list, description="Step-by-step execution instructions")
    precautions: List[str] = Field(default_factory=list)
    kpis: List[str] = Field(default_factory=list, description="Success metrics for this task")

    metadata: Dict[str, Any] = Field(default_factory=dict)


class DailyPlan(BaseModel):
    """All tasks scheduled for a single day."""
    plan_date: date
    tasks: List[ScheduledTask]
    total_labor_units_required: int
    total_water_required_liters: float
    estimated_total_duration_minutes: int
    critical_tasks_count: int
    notes: List[str] = Field(default_factory=list)


class TaskPlan(BaseModel):
    """Complete output from the Task Scheduler Agent."""
    plan_id: str
    request_id: str
    farm_id: str
    generated_at: datetime
    planning_horizon_days: int

    daily_plans: List[DailyPlan]
    all_tasks: List[ScheduledTask]

    total_tasks_scheduled: int
    total_tasks_delayed: int
    total_tasks_skipped: int
    critical_tasks: List[ScheduledTask]
    conflicts_detected: List[ConflictRecord]

    execution_summary: str
    warnings: List[str] = Field(default_factory=list)
    agent_version: str = Field("1.0.0")

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}


# ─────────────────────────────────────────────────────────────────────────────
# API REQUEST / RESPONSE WRAPPERS
# ─────────────────────────────────────────────────────────────────────────────

class ScheduleRequest(BaseModel):
    """HTTP API request body."""
    scheduler_input: SchedulerInput
    callback_url: Optional[str] = None
    priority_override: Optional[Dict[str, float]] = None


class ScheduleResponse(BaseModel):
    """HTTP API response body."""
    success: bool
    request_id: str
    plan: Optional[TaskPlan] = None
    error: Optional[str] = None
    processing_time_ms: float