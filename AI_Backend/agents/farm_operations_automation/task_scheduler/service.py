"""
Task Scheduler Agent — Engine
==============================
Turns what the specialist agents found into the farmer's day.

Pipeline:
    1. collect   - each agent's output becomes candidate jobs
    2. score     - urgency / risk / impact -> one priority
    3. refuse    - food-safety and human-safety rules that are never bent
    4. weather   - move a job to a day it can actually be done
    5. resources - labour, water and equipment the farm really has
    6. conflicts - two jobs competing for the same day
    7. slots     - a real start time, respecting gaps between jobs
    8. guidance  - what to do, what not to do, what waiting costs
    9. plan      - the day, with one headline and one first job

The engine is pure: no database, no network, no calls to other agents. The
caller passes every agent's output in one payload, so the same input always
produces the same plan.
"""

from __future__ import annotations

import logging
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from AI_Backend.agents.farm_operations_automation.task_scheduler.config import (
    AGENT_VERSION,
    CATEGORY_CONFIG,
    DEFAULT_PHI_DAYS,
    DEFAULT_REI_HOURS,
    DELAY_COST_PER_DAY,
    DELAY_ESCALATE_AT,
    DEPENDENCY_GAP_HOURS,
    FROST_BLOCKS,
    FROST_TMIN_C,
    FROZEN_GROUND_TMAX_C,
    GALE_WIND_KMH,
    HEAT_DANGER_TEMP_C,
    HEAT_STRESS_TEMP_C,
    MAX_TASKS_PER_DAY,
    MAX_WORK_HOURS_PER_DAY,
    PHI_HARD_BLOCK,
    PRIORITY_BANDS,
    RAIN_BLOCKS_FIELD_MM,
    RAIN_COVERS_IRRIGATION,
    RAIN_LEACHES_FERT_MM,
    RAIN_PROBABILITY_MIN,
    RAIN_WETS_CANOPY_MM,
    SLOT_GRANULARITY_MIN,
    SOURCE_TRUST,
    SPRAY_TEMP_MAX_C,
    SPRAY_TEMP_MIN_C,
    SPRAY_WIND_MAX_KMH,
    WEIGHT_IMPACT,
    WEIGHT_RISK,
    WEIGHT_URGENCY,
)
from AI_Backend.agents.farm_operations_automation.task_scheduler.playbook import build_guidance
from AI_Backend.agents.farm_operations_automation.task_scheduler.schemas import (
    AgentSource,
    ConflictRecord,
    CropSelectorAgentData,
    DailyPlan,
    IrrigationAgentData,
    MarketIntelligenceAgentData,
    PestDiseaseAgentData,
    Priority,
    RefusedTask,
    ResourcesRequired,
    ScheduledTask,
    SchedulerInput,
    SoilHealthAgentData,
    TaskCategory,
    TaskPlan,
    TaskStatus,
    WeatherAgentData,
    WeatherForecastDay,
)

logger = logging.getLogger("farmxpert.task_scheduler")

SAFETY_NOTES: Dict[str, List[str]] = {
    "pest_control": [
        "Wear gloves, goggles and a mask, and keep children and animals out of the field.",
        "Stand so the wind carries the spray away from you, never into your face.",
        "Wash with soap and change clothes immediately after finishing.",
    ],
    "harvesting": ["Take shade breaks and drink water - harvest days are long and hot."],
    "soil_preparation": ["Stay clear of the implement while the tractor is running; never adjust it in gear."],
    "weeding": ["Drink water every half hour; most heat illness happens during long weeding days."],
    "pruning": ["Have someone hold the ladder, and never cut above shoulder height while standing on it."],
}


@dataclass
class _Rec:
    """A candidate job as it moves through the pipeline."""
    rec_id: str
    source_agent: AgentSource
    category: TaskCategory
    title: str
    description: str

    urgency: float
    risk: float
    impact: float

    duration_minutes: int = 60
    preferred_date: Optional[date] = None
    preferred_timing: Optional[str] = None
    requires_dry_weather: bool = False
    labor_units_required: int = 1
    requires_labor: bool = True
    equipment_required: List[str] = field(default_factory=list)
    water_volume_liters: float = 0.0
    payload: Dict[str, Any] = field(default_factory=dict)

    # Safety data carried from the source agent
    phi_days: Optional[int] = None
    rei_hours: Optional[float] = None
    bee_toxic: bool = False

    why_now: str = ""
    situations: List[str] = field(default_factory=list)

    # Filled by the pipeline
    priority_score: float = 0.0
    priority: Priority = Priority.MEDIUM
    decision: str = "execute_now"
    reason: str = ""
    blocked_by: List[str] = field(default_factory=list)
    original_date: Optional[date] = None
    scheduled_start: Optional[datetime] = None
    scheduled_end: Optional[datetime] = None
    delay_until_date: Optional[date] = None
    skip_reason: Optional[str] = None
    weather_constraint_applied: bool = False
    resource_constraint_applied: bool = False


@dataclass
class _DayView:
    """Everything the scheduler needs to know about one day, in farm terms."""
    day: date
    forecast: Optional[WeatherForecastDay]

    @property
    def known(self) -> bool:
        return self.forecast is not None

    @property
    def rain_mm(self) -> float:
        f = self.forecast
        if f is None:
            return 0.0
        # A forecast amount only counts when the chance is meaningful; a
        # 20 % chance of 30 mm is not a reason to cancel today's work.
        if f.rain_probability_percent and f.rain_probability_percent < RAIN_PROBABILITY_MIN:
            return 0.0
        return float(f.rainfall_mm or 0.0)

    @property
    def wind_kmh(self) -> float:
        return float(self.forecast.wind_speed_kmh or 0.0) if self.forecast else 0.0

    @property
    def tmax(self) -> Optional[float]:
        return self.forecast.temp_max_c if self.forecast else None

    @property
    def tmin(self) -> Optional[float]:
        return self.forecast.temp_min_c if self.forecast else None

    @property
    def frozen(self) -> bool:
        return self.tmax is not None and self.tmax <= FROZEN_GROUND_TMAX_C

    @property
    def frost(self) -> bool:
        f = self.forecast
        if f is None:
            return False
        return bool(f.frost_risk) or (f.temp_min_c is not None and f.temp_min_c <= FROST_TMIN_C)

    @property
    def gale(self) -> bool:
        return self.wind_kmh >= GALE_WIND_KMH

    @property
    def storm(self) -> bool:
        return bool(self.forecast.storm_warning) if self.forecast else False

    @property
    def heat(self) -> bool:
        f = self.forecast
        if f is None:
            return False
        return bool(f.heat_stress_risk) or (f.temp_max_c or 0.0) >= HEAT_STRESS_TEMP_C

    @property
    def heat_danger(self) -> bool:
        return (self.tmax or 0.0) >= HEAT_DANGER_TEMP_C

    def sprayable(self) -> Tuple[bool, str]:
        """Can a spray land and stay on the leaf today?

        The Weather Watcher already works this out hour by hour. When it has
        sent windows we trust them; otherwise we fall back to the daily
        values, which are coarse but never silently wrong.
        """
        f = self.forecast
        if f is None:
            return True, ""
        if f.spray_windows:
            return True, ""
        if self.wind_kmh > SPRAY_WIND_MAX_KMH:
            return False, f"wind is {self.wind_kmh:.0f} km/h, above the {SPRAY_WIND_MAX_KMH:.0f} km/h limit - spray would drift"
        if self.rain_mm >= RAIN_WETS_CANOPY_MM:
            return False, f"about {self.rain_mm:.0f} mm of rain would wash the spray off before it works"
        # Daily max above the limit still leaves a usable morning, so only a
        # day that is hot from dawn is refused outright.
        if self.tmin is not None and self.tmin > SPRAY_TEMP_MAX_C:
            return False, f"it does not drop below {self.tmin:.0f} C even at night - spray would evaporate"
        if self.tmax is not None and self.tmax < SPRAY_TEMP_MIN_C:
            return False, f"it stays below {SPRAY_TEMP_MIN_C:.0f} C all day - the crop will not take the spray up"
        return True, ""


class TaskSchedulerService:
    """Stateless planning engine. Safe to instantiate per request."""

    VERSION = AGENT_VERSION

    def __init__(self) -> None:
        self._days: Dict[date, _DayView] = {}
        self._conflicts: List[ConflictRecord] = []
        self._refused: List[RefusedTask] = []
        self._warnings: List[str] = []
        self._now: datetime = datetime.now(timezone.utc)
        self._inp: Optional[SchedulerInput] = None
        self._crop: Optional[str] = None
        self._field_situations: List[str] = []

    # ── entry point ─────────────────────────────────────────────────────

    def run(self, inp: SchedulerInput) -> TaskPlan:
        self._reset()
        self._inp = inp
        self._now = inp.farm.current_timestamp
        if self._now.tzinfo is None:
            self._now = self._now.replace(tzinfo=timezone.utc)
        self._crop = (inp.farm.current_crop or "").strip().lower() or None

        if inp.weather_agent:
            self._days = {f.date: _DayView(f.date, f) for f in inp.weather_agent.forecast}
        self._field_situations = self._read_situations(inp)

        recs = self._collect(inp)
        if not recs:
            self._warnings.append("Nothing needs doing from the information provided.")

        self._score(recs)
        recs.sort(key=lambda r: r.priority_score, reverse=True)

        recs = self._refuse_unsafe(recs)
        self._apply_weather(recs)
        self._apply_resources(recs)
        self._resolve_conflicts(recs)
        self._assign_slots(recs)

        tasks = [self._to_task(r) for r in recs]
        plan = self._build_plan(tasks)
        logger.info("Plan %s | scheduled=%d delayed=%d skipped=%d refused=%d",
                    plan.plan_id, plan.total_tasks_scheduled, plan.total_tasks_delayed,
                    plan.total_tasks_skipped, len(plan.refused_tasks))
        return plan

    # ── stage 1: collect ────────────────────────────────────────────────

    def _collect(self, inp: SchedulerInput) -> List[_Rec]:
        today = self._now.date()
        recs: List[_Rec] = []
        if inp.irrigation_agent:
            recs += self._from_irrigation(inp.irrigation_agent, today)
        if inp.pest_disease_agent and inp.pest_disease_agent.threat_detected:
            recs += self._from_pest(inp.pest_disease_agent, today)
        if inp.soil_health_agent:
            recs += self._from_soil(inp.soil_health_agent, today)
        if inp.weather_agent:
            recs += self._from_weather(inp.weather_agent, today)
        if inp.crop_selector_agent:
            recs += self._from_crop(inp.crop_selector_agent, today)
        if inp.market_intelligence_agent:
            recs += self._from_market(inp.market_intelligence_agent, today)
        return recs

    def _new(self, prefix: str, source: AgentSource, category: TaskCategory,
             **kwargs) -> _Rec:
        """Build a job, taking defaults for the category from config."""
        cfg = CATEGORY_CONFIG.get(category.value, CATEGORY_CONFIG["other"])
        kwargs.setdefault("duration_minutes", cfg["duration_min"])
        kwargs.setdefault("labor_units_required", cfg["labor"])
        kwargs.setdefault("equipment_required", list(cfg["equipment"]))
        kwargs.setdefault("preferred_timing", cfg["preferred_timing"])
        kwargs.setdefault("requires_dry_weather", cfg["dry_hours_after"] > 0)
        kwargs.setdefault("why_now", cfg["why"])
        return _Rec(rec_id=f"{prefix}-{uuid.uuid4().hex[:8]}",
                    source_agent=source, category=category, **kwargs)

    def _from_irrigation(self, ir: IrrigationAgentData, today: date) -> List[_Rec]:
        out: List[_Rec] = []
        moisture = ir.soil_moisture_current_percent
        stage = (self._inp.farm.growth_stage or "").lower()
        critical_stage = stage in {"flowering", "fruiting", "pegging", "grain_filling", "tuber_bulking"}

        for item in ir.schedule:
            if not item.irrigation_required:
                continue

            volume = item.water_volume_liters or 0.0
            area = self._inp.farm.total_area_hectares
            if volume <= 0 and item.water_depth_mm and area:
                volume = float(item.water_depth_mm) * float(area) * 10_000.0
            duration = int(round((item.duration_hours or 1.5) * 60))

            urgency, why = 6.5, "Soil moisture has fallen to where the crop starts to hold back growth."
            if moisture is not None and moisture < 25:
                urgency, why = 9.0, "The root zone is nearly dry - the crop is losing yield every day now."
            elif moisture is not None and moisture < 40:
                urgency = 7.5
            if critical_stage:
                urgency = max(urgency, 8.0)
                why = (f"The crop is at {stage} - water stress now cannot be made up later in the season.")

            situations = []
            if moisture is not None and moisture < 25:
                situations.append("low_moisture")
            if critical_stage:
                situations.append("critical_stage")

            out.append(self._new(
                "irr", AgentSource.IRRIGATION, TaskCategory.IRRIGATION,
                title=f"Irrigate - {item.method} ({item.water_depth_mm:.0f} mm)"
                      if item.water_depth_mm else f"Irrigate - {item.method}",
                description=item.reason or "Apply the planned irrigation depth.",
                urgency=urgency, risk=7.0, impact=8.0,
                duration_minutes=max(15, duration),
                preferred_date=item.date,
                preferred_timing=(item.timing or "morning").lower(),
                equipment_required=[f"{item.method}_set"],
                water_volume_liters=volume,
                why_now=why, situations=situations,
                payload={"method": item.method, "water_depth_mm": item.water_depth_mm,
                         "duration_hours": item.duration_hours},
            ))
        return out

    def _from_pest(self, p: PestDiseaseAgentData, today: date) -> List[_Rec]:
        urgency = max(5.0, min(10.0, p.severity))
        risk = max(5.0, min(10.0, p.severity * 1.05))
        impact = max(5.0, min(10.0, 6.0 + p.affected_area_percent / 20.0))
        threat = (p.threat_type or "pest").replace("_", " ")

        spread = ("It is on about {:.0f}% of the field. Left alone, an outbreak this size "
                  "usually doubles within a week.").format(p.affected_area_percent)
        return [self._new(
            "pest", AgentSource.PEST_DISEASE, TaskCategory.PEST_CONTROL,
            title=f"Treat {threat}" + (f" with {p.chemical_name}" if p.chemical_name else ""),
            description=f"Severity {p.severity:.1f}/10 on {p.affected_area_percent:.0f}% of the field. "
                        f"Treatment: {p.treatment_type or 'as recommended'}.",
            urgency=urgency, risk=risk, impact=impact,
            preferred_date=today,
            requires_dry_weather=p.requires_dry_conditions,
            phi_days=p.pre_harvest_interval_days,
            rei_hours=p.re_entry_interval_hours,
            bee_toxic=p.bee_toxic,
            why_now=spread,
            payload={"threat_type": p.threat_type, "severity": p.severity,
                     "affected_area_percent": p.affected_area_percent,
                     "chemical_name": p.chemical_name,
                     "application_rate_ml_per_liter": p.application_rate_ml_per_liter,
                     "pre_harvest_interval_days": p.pre_harvest_interval_days,
                     "re_entry_interval_hours": p.re_entry_interval_hours},
        )]

    def _from_soil(self, s: SoilHealthAgentData, today: date) -> List[_Rec]:
        out: List[_Rec] = []
        severity_of = {a.type: (a.severity or "medium").lower() for a in s.alerts}
        urgency_for = {"critical": 9.0, "high": 7.5, "medium": 5.5, "low": 3.5}

        for fert in s.fertilizers:
            sev = severity_of.get(fert.triggered_by or "", "medium")
            urgency = urgency_for.get(sev, 5.5)
            out.append(self._new(
                "fert", AgentSource.SOIL_HEALTH, TaskCategory.FERTILIZATION,
                title=f"Apply {fert.display_name} - {fert.dosage}",
                description=f"{fert.dosage}, {fert.timing}. Method: {fert.method.replace('_', ' ')}.",
                urgency=urgency, risk=urgency * 0.9, impact=7.5,
                preferred_date=today,
                equipment_required=["spreader"] if "soil" in fert.method else ["sprayer"],
                why_now=("The soil test shows this nutrient is short. Correcting it now, while the "
                         "crop can still use it, is far cheaper than a yield loss at harvest."),
                payload={"fertilizer": fert.fertilizer, "display_name": fert.display_name,
                         "dosage": fert.dosage, "method": fert.method,
                         "cautions": fert.cautions, "triggered_by": fert.triggered_by},
            ))

        remedied = {f.triggered_by for f in s.fertilizers}
        for alert in s.alerts:
            if (alert.severity or "").lower() not in {"high", "critical"} or alert.type in remedied:
                continue
            out.append(self._new(
                "soil", AgentSource.SOIL_HEALTH, TaskCategory.MONITORING,
                title=f"Check soil - {alert.type.replace('_', ' ')}",
                description=alert.message,
                urgency=7.5 if (alert.severity or "").lower() == "critical" else 6.0,
                risk=6.0, impact=5.0,
                preferred_date=today,
                why_now="The soil reading is outside the safe range and nothing has been applied for it yet.",
                payload={"alert_type": alert.type},
            ))
        return out

    def _from_weather(self, w: WeatherAgentData, today: date) -> List[_Rec]:
        urgency_for = {"critical": 9.0, "high": 7.5, "medium": 5.0, "low": 3.0}
        out: List[_Rec] = []
        for alert in w.alerts:
            sev = (alert.severity or "medium").lower()
            if sev in {"low", "info"}:
                continue    # advisory only - it belongs in the day's note, not the job list
            urgency = urgency_for.get(sev, 5.0)
            out.append(self._new(
                "wx", AgentSource.WEATHER, TaskCategory.MONITORING,
                title=f"Prepare for {alert.type.replace('_', ' ')}",
                description=alert.message,
                urgency=urgency, risk=urgency * 0.9, impact=5.0,
                duration_minutes=30,
                preferred_date=alert.date or today,
                why_now="The forecast gives you a short window to protect the crop before this arrives.",
                payload={"alert_type": alert.type, "recommendations": alert.recommendations},
            ))
        return out

    def _from_crop(self, c: CropSelectorAgentData, today: date) -> List[_Rec]:
        out: List[_Rec] = []
        in_window = (c.planting_window_start and c.planting_window_end
                     and c.planting_window_start <= today <= c.planting_window_end)
        no_crop = not self._inp.farm.current_crop

        if c.recommended_crops and (in_window or no_crop):
            top = c.recommended_crops[0]
            start = c.planting_window_start or today
            if start < today:
                start = today
            days_left = (c.planting_window_end - today).days if c.planting_window_end else None
            urgency = 5.0
            why = f"{top.crop_name.title()} scored highest for this field this season."
            if days_left is not None and days_left <= 7:
                urgency = 7.5
                why = (f"Only {days_left} day(s) of the sowing window are left. Sowing after it "
                       "closes shortens the season and costs yield.")

            out.append(self._new(
                "prep", AgentSource.CROP_SELECTOR, TaskCategory.SOIL_PREP,
                title=f"Prepare the field for {top.crop_name}",
                description=f"Seedbed preparation for {top.crop_name}"
                            + (f" (variety {top.variety})" if top.variety else "")
                            + f". Suitability {top.suitability_score:.1f}/10.",
                urgency=urgency, risk=4.0, impact=7.5,
                preferred_date=start,
                why_now=why,
                payload={"crop_name": top.crop_name, "variety": top.variety},
            ))
            out.append(self._new(
                "sow", AgentSource.CROP_SELECTOR, TaskCategory.PLANTING,
                title=f"Sow {top.crop_name}",
                description=f"Sow {top.crop_name} at the recommended spacing. "
                            f"Season length about {top.duration_days or 'n/a'} days.",
                urgency=urgency + 0.5, risk=4.5, impact=8.0,
                preferred_date=start + timedelta(days=1),
                why_now=why,
                payload={"crop_name": top.crop_name, "variety": top.variety},
            ))

        days_out = c.days_to_harvest if c.days_to_harvest is not None else self._inp.farm.days_to_harvest
        if days_out is not None and 0 <= days_out <= 5:
            out.append(self._new(
                "harv", AgentSource.CROP_SELECTOR, TaskCategory.HARVESTING,
                title="Get ready to harvest",
                description=f"Harvest is about {days_out} day(s) away. Confirm maturity, "
                            "line up labour, machinery and transport.",
                urgency=7.0, risk=5.0, impact=8.5,
                duration_minutes=60,
                preferred_date=today + timedelta(days=max(0, days_out - 1)),
                why_now="Everything must be ready before the crop is ready - a harvest that waits for "
                        "labour loses grade in the field.",
                situations=["near_harvest"],
                payload={"days_to_harvest": days_out},
            ))
        return out

    def _from_market(self, m: MarketIntelligenceAgentData, today: date) -> List[_Rec]:
        """Market data is informational by default; a task appears only when the
        caller passes an explicit action."""
        action = (m.recommended_action or "").upper()
        if not action or action == "HOLD":
            return []
        titles = {"SELL_NOW": f"Sell {m.commodity}",
                  "SELL_IN_OTHER_MANDI": f"Take {m.commodity} to a better mandi"}
        scores = {"SELL_NOW": (7.5, 4.0, 8.0), "SELL_IN_OTHER_MANDI": (6.0, 4.5, 7.0)}
        urgency, risk, impact = scores.get(action, (5.0, 3.5, 6.0))

        parts = [m.reason or ""]
        if m.current_modal_price_per_quintal is not None:
            parts.append(f"Today's modal price is about Rs {m.current_modal_price_per_quintal:.0f}/quintal.")
        if m.predicted_trend:
            parts.append(f"The forecast trend is {m.predicted_trend}.")

        return [self._new(
            "mkt", AgentSource.MARKET_INTELLIGENCE, TaskCategory.MARKET_ACTION,
            title=titles.get(action, f"Market action: {action}"),
            description=" ".join(p for p in parts if p).strip() or f"Market action for {m.commodity}.",
            urgency=urgency, risk=risk, impact=impact,
            preferred_date=today,
            equipment_required=["transport"] if action == "SELL_IN_OTHER_MANDI" else [],
            why_now="Price windows close faster than field windows.",
            payload={"commodity": m.commodity, "recommended_action": action,
                     "current_modal_price_per_quintal": m.current_modal_price_per_quintal,
                     "predicted_price_per_quintal": m.predicted_price_per_quintal},
        )]

    def _read_situations(self, inp: SchedulerInput) -> List[str]:
        """Field-wide conditions that colour every job today."""
        out: List[str] = []
        today = _DayView(self._now.date(), self._days.get(self._now.date(), _DayView(self._now.date(), None)).forecast)
        if today.known:
            if today.heat_danger:
                out.append("heat_danger")
            elif today.heat:
                out.append("heat_day")
            if today.frozen:
                out.append("frozen_ground")
            elif today.frost:
                out.append("frost_night")
            if today.gale:
                out.append("gale_wind")
            if today.rain_mm >= RAIN_BLOCKS_FIELD_MM:
                out.append("wet_field")
            elif today.rain_mm >= RAIN_WETS_CANOPY_MM:
                out.append("rain_coming")

        soil = inp.soil_health_agent
        if soil:
            for alert in soil.alerts:
                kind = (alert.type or "").lower()
                if "salin" in kind or "conductivity" in kind:
                    out.append("saline_soil")
                if "acid" in kind or kind.endswith("ph_low"):
                    out.append("acid_soil")
        ir = inp.irrigation_agent
        if ir and ir.soil_moisture_current_percent is not None:
            if ir.soil_moisture_current_percent < 25:
                out.append("low_moisture")
            elif ir.soil_moisture_current_percent > 90:
                out.append("waterlogged")
        if (inp.farm.days_to_harvest is not None and inp.farm.days_to_harvest <= 14):
            out.append("near_harvest")
        return list(dict.fromkeys(out))

    # ── stage 2: score ──────────────────────────────────────────────────

    def _score(self, recs: List[_Rec]) -> None:
        for r in recs:
            trust = SOURCE_TRUST.get(r.source_agent.value, 1.0)
            raw = r.urgency * WEIGHT_URGENCY + r.risk * WEIGHT_RISK + r.impact * WEIGHT_IMPACT
            r.priority_score = round(min(10.0, raw * trust), 3)
            r.priority = self._band(r.priority_score)
            r.original_date = r.preferred_date or self._now.date()
            r.reason = r.why_now or ""

    @staticmethod
    def _band(score: float) -> Priority:
        for name, floor in PRIORITY_BANDS:
            if score >= floor:
                return Priority(name)
        return Priority.DEFERRED

    # ── stage 3: safety refusals ────────────────────────────────────────

    def _refuse_unsafe(self, recs: List[_Rec]) -> List[_Rec]:
        """Rules that are refused, never rescheduled.

        A pre-harvest interval is not a preference: produce sprayed inside it
        carries residue above the legal limit, and neither the farmer nor the
        buyer can undo that later. The same holds for a bee-toxic spray on a
        crop in flower - the pollination lost is this season's fruit set.
        """
        kept: List[_Rec] = []
        days_out = self._inp.farm.days_to_harvest

        for r in recs:
            if r.category != TaskCategory.PEST_CONTROL:
                kept.append(r)
                continue

            phi = r.phi_days if r.phi_days is not None else DEFAULT_PHI_DAYS
            if PHI_HARD_BLOCK and days_out is not None and days_out < phi:
                self._refused.append(RefusedTask(
                    title=r.title, category=r.category,
                    rule=f"Pre-harvest interval {phi} days",
                    explanation=(f"Harvest is about {days_out} day(s) away, but this product needs "
                                 f"{phi} day(s) between spraying and harvest. Spraying now would leave "
                                 "residue above the legal limit - the produce could be rejected at the "
                                 "mandi and is not safe to eat."),
                    what_to_do_instead=("Ask your dealer for a product with a shorter pre-harvest "
                                        "interval, use a biological control, or accept the damage and "
                                        "harvest on time."),
                ))
                continue

            if r.bee_toxic and self._inp.farm.in_flower:
                self._refused.append(RefusedTask(
                    title=r.title, category=r.category,
                    rule="Bee-toxic spray on a flowering crop",
                    explanation=("The crop is in flower. This product kills the bees pollinating it, "
                                 "so you would lose the fruit set you are trying to protect."),
                    what_to_do_instead=("Wait until flowering is over, or use a product that is safe "
                                        "for pollinators and apply it in the evening."),
                ))
                continue

            kept.append(r)
        return kept

    # ── stage 4: weather ────────────────────────────────────────────────

    def _day(self, day: date) -> _DayView:
        view = self._days.get(day)
        return view if view is not None else _DayView(day, None)

    def _blockers(self, r: _Rec, day: date) -> List[str]:
        """Plain-language reasons this job cannot be done on this day."""
        view = self._day(day)
        if not view.known:
            return []
        cfg = CATEGORY_CONFIG.get(r.category.value, CATEGORY_CONFIG["other"])
        out: List[str] = []

        if view.gale:
            out.append(f"winds of {view.wind_kmh:.0f} km/h make open-field work unsafe")
        if view.storm and r.priority != Priority.CRITICAL:
            out.append("a storm is forecast")

        if r.category == TaskCategory.IRRIGATION:
            planned_mm = r.payload.get("water_depth_mm") or 0.0
            if view.frozen:
                out.append("the ground is frozen, so water cannot soak in")
            elif planned_mm and view.rain_mm >= float(planned_mm) * RAIN_COVERS_IRRIGATION:
                out.append(f"about {view.rain_mm:.0f} mm of rain is expected, which covers this irrigation")
            elif not planned_mm and view.rain_mm >= RAIN_BLOCKS_FIELD_MM:
                out.append(f"about {view.rain_mm:.0f} mm of rain is expected")

        if r.category == TaskCategory.FERTILIZATION:
            if view.rain_mm >= RAIN_LEACHES_FERT_MM:
                out.append(f"about {view.rain_mm:.0f} mm of rain would wash the nutrient below the roots")
            if view.frozen:
                out.append("the ground is frozen - nothing applied now will get in")

        if cfg["spray"]:
            ok, why = view.sprayable()
            if not ok:
                out.append(why)

        if cfg["dry_hours_after"] > 0 and r.category != TaskCategory.FERTILIZATION:
            if view.rain_mm >= RAIN_WETS_CANOPY_MM and "wash" not in " ".join(out):
                out.append(f"about {view.rain_mm:.0f} mm of rain would wash it off before it works")

        if view.frost and r.category.value in FROST_BLOCKS:
            out.append("frost is likely, which would damage exposed plants and wet soil")

        if r.category in {TaskCategory.SOIL_PREP, TaskCategory.PLANTING, TaskCategory.HARVESTING}:
            if view.rain_mm >= RAIN_BLOCKS_FIELD_MM:
                out.append(f"about {view.rain_mm:.0f} mm of rain leaves the field too wet for machinery")

        # Heat is a limit on people, not on the crop. A hot day still has a
        # cool morning, so only dangerous heat blocks the day outright.
        if cfg["heat_sensitive"] and view.heat_danger:
            out.append(f"{view.tmax:.0f} C is dangerous for anyone working in the open all day")
        return out

    def _apply_weather(self, recs: List[_Rec]) -> None:
        if not self._days:
            return
        horizon = self._inp.planning_horizon_days
        today = self._now.date()

        for r in recs:
            if r.decision == "skip":
                continue
            target = r.preferred_date or today
            blockers = self._blockers(r, target)
            if not blockers:
                continue

            r.weather_constraint_applied = True
            r.blocked_by = blockers

            moved = None
            for offset in range(1, horizon + 1):
                candidate = target + timedelta(days=offset)
                if candidate > today + timedelta(days=horizon):
                    break
                if not self._blockers(r, candidate):
                    moved = candidate
                    break

            if moved is None:
                r.decision = "skip"
                r.skip_reason = ("No day in the plan is suitable: "
                                 + _join(blockers) + ".")
                r.reason = r.why_now
            else:
                r.preferred_date = moved
                r.reason = r.why_now

    # ── stage 5: resources ──────────────────────────────────────────────

    def _apply_resources(self, recs: List[_Rec]) -> None:
        res = self._inp.resources
        water_left = res.water_available_liters
        labour_by_day: Dict[date, int] = defaultdict(int)

        for r in recs:
            if r.decision != "execute_now":
                continue
            day = r.preferred_date or self._now.date()

            if r.requires_labor and r.labor_units_required > res.labor_units_available:
                if r.priority in (Priority.CRITICAL, Priority.HIGH):
                    self._warnings.append(
                        f"'{r.title}' needs {r.labor_units_required} people and only "
                        f"{res.labor_units_available} are available. It is too important to postpone - "
                        "arrange extra hands or expect it to take longer.")
                else:
                    self._delay(r, day + timedelta(days=1),
                                f"it needs {r.labor_units_required} people and only "
                                f"{res.labor_units_available} are available")
                    continue
            labour_by_day[day] += r.labor_units_required

            if r.category == TaskCategory.IRRIGATION and r.water_volume_liters > 0 \
                    and res.water_available_liters > 0:
                if r.water_volume_liters > water_left:
                    if r.priority == Priority.CRITICAL:
                        self._warnings.append(
                            f"'{r.title}' needs {r.water_volume_liters:,.0f} litres but only "
                            f"{max(0.0, water_left):,.0f} litres are left. Irrigate the most "
                            "sensitive part of the field first rather than spreading it thin.")
                    else:
                        self._delay(r, day + timedelta(days=1),
                                    f"there is not enough water left ({max(0.0, water_left):,.0f} of "
                                    f"{r.water_volume_liters:,.0f} litres)")
                        continue
                water_left -= r.water_volume_liters

            missing = [e for e in r.equipment_required if e not in res.equipment_available]
            if missing and res.equipment_available:
                readable = _join([m.replace('_', ' ') for m in missing])
                if r.priority in (Priority.CRITICAL, Priority.HIGH):
                    self._warnings.append(
                        f"'{r.title}' needs {readable}, which is not on the farm. "
                        "Arrange to hire or borrow it today.")
                else:
                    self._delay(r, day + timedelta(days=1), f"{readable} is not available")

    def _delay(self, r: _Rec, until: date, because: str) -> None:
        r.decision = "delay"
        r.delay_until_date = until
        r.resource_constraint_applied = True
        r.blocked_by.append(because)

    # ── stage 6: conflicts ──────────────────────────────────────────────

    def _resolve_conflicts(self, recs: List[_Rec]) -> None:
        """Two jobs that really are the same job on the same day.

        Two different fertilizers or a split dose are not a conflict - a farm
        legitimately does two of those in one day. Only identical work is
        collapsed.
        """
        buckets: Dict[Tuple[str, date], List[_Rec]] = defaultdict(list)
        for r in recs:
            if r.decision != "execute_now":
                continue
            key = (r.title.strip().lower(), r.preferred_date or self._now.date())
            buckets[key].append(r)

        for (title, day), group in buckets.items():
            if len(group) <= 1:
                continue
            group.sort(key=lambda x: x.priority_score, reverse=True)
            winner, duplicates = group[0], group[1:]
            for dup in duplicates:
                dup.decision = "skip"
                dup.skip_reason = f"The same job is already planned for {day.isoformat()}."
                self._conflicts.append(ConflictRecord(
                    conflict_id=f"conflict-{uuid.uuid4().hex[:8]}",
                    conflicting_task_ids=[winner.rec_id, dup.rec_id],
                    conflict_type="duplicate_task",
                    description=f"'{winner.title}' was suggested twice for {day.isoformat()}.",
                    resolution="merge",
                    resolution_reason="Kept one; the second would have been the same work twice.",
                ))

    # ── stage 7: slots ──────────────────────────────────────────────────

    def _assign_slots(self, recs: List[_Rec]) -> None:
        res = self._inp.resources
        start_h, start_m = _hhmm(res.working_hours_start)
        end_h, end_m = _hhmm(res.working_hours_end)
        today = self._now.date()
        last_day = today + timedelta(days=self._inp.planning_horizon_days)

        booked: Dict[date, List[Tuple[datetime, datetime, TaskCategory]]] = defaultdict(list)
        count: Dict[date, int] = defaultdict(int)
        minutes: Dict[date, float] = defaultdict(float)

        for r in recs:
            if r.decision != "execute_now":
                continue
            target = max(r.preferred_date or today, today)
            placed = False

            for offset in range(0, self._inp.planning_horizon_days + 1):
                day = target + timedelta(days=offset)
                if day > last_day:
                    break
                if count[day] >= MAX_TASKS_PER_DAY:
                    continue
                if (minutes[day] + r.duration_minutes) / 60.0 > MAX_WORK_HOURS_PER_DAY:
                    continue
                if offset and self._blockers(r, day):
                    continue

                tz = self._now.tzinfo
                work_start = datetime(day.year, day.month, day.day, start_h, start_m, tzinfo=tz)
                work_end = datetime(day.year, day.month, day.day, end_h, end_m, tzinfo=tz)

                # On a hot day, heat-sensitive work stops before the worst of it.
                view = self._day(day)
                if view.heat and CATEGORY_CONFIG[r.category.value]["heat_sensitive"]:
                    work_end = min(work_end, work_start.replace(hour=11, minute=0))
                if r.preferred_timing == "evening":
                    work_start = max(work_start, work_end - timedelta(hours=4))
                if day == today:
                    work_start = max(work_start, _ceil_to_slot(self._now))

                earliest = self._after_gaps(r.category, booked[day], work_start)
                slot = self._first_free(booked[day], earliest, work_end, r.duration_minutes)
                if slot is None:
                    continue

                if day != target and not r.blocked_by:
                    # Pushed by the day's capacity or by a required gap after
                    # another job - say so, or the new date looks arbitrary.
                    gap_after = [done.value.replace("_", " ")
                                 for _s, _e, done in booked[target]
                                 if DEPENDENCY_GAP_HOURS.get(f"{done.value}->{r.category.value}")]
                    if gap_after:
                        r.blocked_by.append(
                            f"it has to wait after {_join(sorted(set(gap_after)))}")
                    else:
                        r.blocked_by.append("the earlier day was already full")

                end = slot + timedelta(minutes=r.duration_minutes)
                booked[day].append((slot, end, r.category))
                count[day] += 1
                minutes[day] += r.duration_minutes
                r.scheduled_start, r.scheduled_end = slot, end
                placed = True
                break

            if not placed:
                self._delay(r, last_day + timedelta(days=1),
                            f"the next {self._inp.planning_horizon_days} day(s) are already full")
                r.resource_constraint_applied = False

    @staticmethod
    def _after_gaps(category: TaskCategory,
                    booked: List[Tuple[datetime, datetime, TaskCategory]],
                    work_start: datetime) -> datetime:
        earliest = work_start
        for _start, end, done in booked:
            gap = DEPENDENCY_GAP_HOURS.get(f"{done.value}->{category.value}", 0.0)
            if gap:
                earliest = max(earliest, end + timedelta(hours=gap))
        return earliest

    @staticmethod
    def _first_free(booked: List[Tuple[datetime, datetime, TaskCategory]],
                    earliest: datetime, work_end: datetime, duration: int) -> Optional[datetime]:
        cursor = _ceil_to_slot(earliest)
        for start, end, _cat in sorted(booked, key=lambda x: x[0]):
            if cursor + timedelta(minutes=duration) <= start:
                return cursor
            if end > cursor:
                cursor = _ceil_to_slot(end)
        return cursor if cursor + timedelta(minutes=duration) <= work_end else None

    # ── stage 8: guidance ───────────────────────────────────────────────

    def _to_task(self, r: _Rec) -> ScheduledTask:
        if r.decision == "execute_now" and r.scheduled_start and r.scheduled_end:
            status, decision = TaskStatus.SCHEDULED, "execute_now"
            on, start, end = r.scheduled_start.date(), r.scheduled_start.strftime("%H:%M"), \
                r.scheduled_end.strftime("%H:%M")
            delay_until = None
        elif r.decision == "delay":
            status, decision = TaskStatus.DELAYED, "delay"
            on, start, end = r.delay_until_date, None, None
            delay_until = r.delay_until_date
        else:
            status, decision = TaskStatus.SKIPPED, "skip"
            on = start = end = delay_until = None

        situations = list(dict.fromkeys(self._field_situations + r.situations))
        guidance = build_guidance(r.category.value, self._crop, situations)

        reason = r.why_now or r.reason
        if r.blocked_by:
            moved_to = on.isoformat() if on else "a later day"
            reason = f"{reason} Moved to {moved_to} because {_join(r.blocked_by)}.".strip()

        return ScheduledTask(
            task_id=f"task-{uuid.uuid4().hex[:10]}",
            source_agent=r.source_agent,
            farm_id=self._inp.farm.farm_id,
            field_id=self._inp.farm.field_id,
            title=r.title,
            description=r.description,
            category=r.category,
            status=status,
            priority=r.priority,
            priority_score=r.priority_score,
            scheduled_date=on,
            scheduled_start_time=start,
            scheduled_end_time=end,
            duration_minutes=r.duration_minutes,
            decision=decision,
            reason=reason or "Part of this field's routine.",
            delay_until_date=delay_until,
            skip_reason=r.skip_reason,
            resources_required=ResourcesRequired(
                labor_units=r.labor_units_required if r.requires_labor else 0,
                water_liters=round(r.water_volume_liters, 2),
                equipment=list(r.equipment_required),
            ),
            instructions=guidance["do"],
            precautions=guidance["do_not"],
            kpis=[],
            why_now=r.why_now,
            do=guidance["do"],
            do_not=guidance["do_not"],
            safety=self._safety_for(r, situations),
            cost_of_delay=self._cost_of_delay(r),
            blocked_by=list(r.blocked_by),
            weather_constraint_applied=r.weather_constraint_applied,
            resource_constraint_applied=r.resource_constraint_applied,
            metadata=r.payload,
        )

    def _safety_for(self, r: _Rec, situations: List[str]) -> List[str]:
        out = list(SAFETY_NOTES.get(r.category.value, []))
        if r.category == TaskCategory.PEST_CONTROL:
            rei = r.rei_hours if r.rei_hours is not None else DEFAULT_REI_HOURS
            out.append(f"Keep everyone out of the field for {rei:.0f} hours after spraying.")
            phi = r.phi_days if r.phi_days is not None else DEFAULT_PHI_DAYS
            out.append(f"Do not harvest for {phi} day(s) after this spray.")
        if "heat_danger" in situations or "heat_day" in situations:
            out.append("Work in the cool hours, drink water often, and do not work alone at midday.")
        return out

    def _cost_of_delay(self, r: _Rec) -> Optional[str]:
        """What waiting actually costs, stated only when the job is waiting."""
        landed = r.delay_until_date or (r.scheduled_start.date() if r.scheduled_start else None)
        if landed is None or r.original_date is None:
            days = 0
        else:
            days = max(0, (landed - r.original_date).days)
        if days <= 0:
            return None

        rate = DELAY_COST_PER_DAY.get(r.category.value, 0.02)
        lost = min(1.0, rate * days)
        phrase = {
            "pest_control": f"{days} day(s) of delay lets the outbreak spread further - "
                            "expect roughly a quarter more damage for each day lost.",
            "irrigation": f"{days} day(s) without water at this stage takes yield you cannot get back.",
            "harvesting": f"{days} day(s) late costs grade and weight in the field.",
            "planting": f"{days} day(s) later leaves the crop that much less season to grow in.",
        }.get(r.category.value,
              f"Waiting {days} day(s) reduces what this job achieves by roughly {lost * 100:.0f}%.")
        if lost >= DELAY_ESCALATE_AT:
            phrase += " Do this first as soon as conditions allow."
        return phrase

    # ── stage 9: the plan ───────────────────────────────────────────────

    def _build_plan(self, tasks: List[ScheduledTask]) -> TaskPlan:
        by_day: Dict[date, List[ScheduledTask]] = defaultdict(list)
        for t in tasks:
            day = t.scheduled_date or t.delay_until_date
            if day:
                by_day[day].append(t)

        daily: List[DailyPlan] = []
        for day in sorted(by_day):
            day_tasks = sorted(by_day[day], key=lambda t: (t.scheduled_start_time or "99:99"))
            notes: List[str] = []
            note = self._weather_note(day)
            if note:
                notes.append(note)
            critical = sum(1 for t in day_tasks if t.priority == Priority.CRITICAL)
            if critical:
                notes.append(f"{critical} job(s) here cannot wait - do them before anything else.")
            daily.append(DailyPlan(
                plan_date=day,
                weather_note=note,
                tasks=day_tasks,
                total_tasks=len(day_tasks),
                critical_tasks=critical,
                total_labor_units=sum(t.resources_required.labor_units for t in day_tasks),
                total_water_liters=round(sum(t.resources_required.water_liters for t in day_tasks), 2),
                estimated_total_duration_minutes=sum(t.duration_minutes for t in day_tasks),
                notes=notes,
            ))

        scheduled = [t for t in tasks if t.status == TaskStatus.SCHEDULED]
        delayed = [t for t in tasks if t.status == TaskStatus.DELAYED]
        skipped = [t for t in tasks if t.status == TaskStatus.SKIPPED]
        critical = [t for t in tasks if t.priority == Priority.CRITICAL]

        today = self._now.date()
        today_tasks = [t for t in scheduled if t.scheduled_date == today]
        first = max(today_tasks or scheduled, key=lambda t: t.priority_score, default=None)

        return TaskPlan(
            plan_id=f"plan-{uuid.uuid4().hex[:10]}",
            request_id=self._inp.request_id,
            farm_id=self._inp.farm.farm_id,
            field_id=self._inp.farm.field_id,
            generated_at=self._now,
            planning_horizon_days=self._inp.planning_horizon_days,
            summary=(f"{len(scheduled)} job(s) planned over {len(daily)} day(s); "
                     f"{len(delayed)} waiting, {len(skipped)} not needed. "
                     f"{len(critical)} cannot wait."),
            headline=self._headline(today_tasks, critical, delayed),
            do_first=first.title if first else None,
            total_tasks_scheduled=len(scheduled),
            total_tasks_delayed=len(delayed),
            total_tasks_skipped=len(skipped),
            daily_plans=daily,
            all_tasks=tasks,
            critical_tasks=critical,
            conflicts_detected=self._conflicts,
            refused_tasks=self._refused,
            warnings=self._warnings,
            agent_version=self.VERSION,
        )

    def _headline(self, today_tasks: List[ScheduledTask],
                  critical: List[ScheduledTask], delayed: List[ScheduledTask]) -> str:
        if self._refused:
            return f"{self._refused[0].title} is not safe to do - {self._refused[0].rule.lower()}."
        if not today_tasks:
            if delayed:
                # Name the real cause: blaming the weather for a water or
                # labour shortage sends the farmer to look at the wrong thing.
                if any(t.weather_constraint_applied for t in delayed):
                    return "Nothing can be done in the field today - the weather has pushed the work back."
                reason = next((t.blocked_by[0] for t in delayed if t.blocked_by), None)
                return (f"Nothing is scheduled today because {reason}." if reason
                        else "Today's work has been pushed back.")
            return "Nothing needs doing in the field today."
        urgent = [t for t in today_tasks if t.priority == Priority.CRITICAL]
        if urgent:
            return f"{len(urgent)} urgent job(s) today - start with {urgent[0].title.lower()}."
        hours = sum(t.duration_minutes for t in today_tasks) / 60.0
        return (f"{len(today_tasks)} job(s) today, about {hours:.0f} hour(s) of work. "
                f"Start with {today_tasks[0].title.lower()}.")

    def _weather_note(self, day: date) -> Optional[str]:
        view = self._day(day)
        if not view.known:
            return None
        bits = [f"{view.tmax:.0f} C high, {view.tmin:.0f} C low"]
        if view.rain_mm >= 1.0:
            bits.append(f"about {view.rain_mm:.0f} mm of rain")
        elif view.forecast.rain_probability_percent:
            bits.append(f"{view.forecast.rain_probability_percent:.0f}% chance of rain")
        bits.append(f"wind {view.wind_kmh:.0f} km/h")
        return "; ".join(bits) + "."

    def _reset(self) -> None:
        self._days, self._conflicts, self._refused = {}, [], []
        self._warnings, self._field_situations = [], []


# ── helpers ─────────────────────────────────────────────────────────────────

def _hhmm(value: str) -> Tuple[int, int]:
    hour, minute = value.split(":")
    return int(hour), int(minute)


def _ceil_to_slot(moment: datetime) -> datetime:
    """Round up to the next quarter hour so start times read naturally."""
    moment = moment.replace(second=0, microsecond=0)
    remainder = moment.minute % SLOT_GRANULARITY_MIN
    if remainder:
        moment += timedelta(minutes=SLOT_GRANULARITY_MIN - remainder)
    return moment


def _join(items: List[str]) -> str:
    items = [i for i in items if i]
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + " and " + items[-1]
