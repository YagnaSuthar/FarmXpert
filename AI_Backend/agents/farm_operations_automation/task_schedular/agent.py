"""
FarmXpert Task Scheduler Agent — Core Agent Logic
==================================================
Transforms specialist agent recommendations into a prioritized,
conflict-free, time-based execution plan.

Architecture:
  SchedulerAgent
    ├── _validate_recommendations()      — staleness + data checks
    ├── _score_recommendations()         — compute priority_score per recommendation
    ├── _apply_weather_constraints()     — delay/skip based on forecast
    ├── _apply_resource_constraints()    — delay/skip based on labor/water
    ├── _resolve_dependencies()          — enforce ordering between tasks
    ├── _detect_and_resolve_conflicts()  — eliminate redundancy & conflicts
    ├── _assign_schedule_slots()         — bin tasks into time windows
    ├── _enrich_tasks()                  — add instructions, KPIs, precautions
    └── _build_plan()                    — assemble final TaskPlan output
"""

from __future__ import annotations

import logging
import uuid
from collections import defaultdict
from datetime import datetime, timedelta, date, timezone
from typing import Dict, List, Optional, Set, Tuple

from config import (
    settings,
    TASK_INSTRUCTIONS,
    TASK_KPIS,
)
from schemas import (
    AgentRecommendation,
    AgentSource,
    ConflictRecord,
    ConflictResolution,
    DailyPlan,
    FarmContext,
    GrowthStage,
    Priority,
    ScheduledTask,
    SchedulerInput,
    TaskCategory,
    TaskPlan,
    TaskStatus,
    WeatherPayload,
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# DECISION RESULT (INTERNAL)
# ─────────────────────────────────────────────────────────────────────────────

class DecisionResult:
    """Internal decision outcome for a single recommendation."""

    __slots__ = (
        "recommendation_id", "decision", "reason", "priority", "priority_score",
        "scheduled_start", "delay_until", "skip_reason",
        "weather_constraint_applied", "dependency_constraint_applied",
        "resource_constraint_applied",
    )

    def __init__(
        self,
        recommendation_id: str,
        decision: str,
        reason: str,
        priority: Priority,
        priority_score: float,
        scheduled_start: Optional[datetime] = None,
        delay_until: Optional[datetime] = None,
        skip_reason: Optional[str] = None,
        weather_constraint_applied: bool = False,
        dependency_constraint_applied: bool = False,
        resource_constraint_applied: bool = False,
    ):
        self.recommendation_id = recommendation_id
        self.decision = decision
        self.reason = reason
        self.priority = priority
        self.priority_score = priority_score
        self.scheduled_start = scheduled_start
        self.delay_until = delay_until
        self.skip_reason = skip_reason
        self.weather_constraint_applied = weather_constraint_applied
        self.dependency_constraint_applied = dependency_constraint_applied
        self.resource_constraint_applied = resource_constraint_applied


# ─────────────────────────────────────────────────────────────────────────────
# TASK SCHEDULER AGENT
# ─────────────────────────────────────────────────────────────────────────────

class TaskSchedulerAgent:
    """
    Core scheduling engine for FarmXpert.

    Responsibilities:
    - Accept multi-agent recommendations
    - Score, prioritize, and resolve conflicts
    - Generate a deterministic, explainable task plan
    """

    VERSION = "1.0.0"

    def __init__(self) -> None:
        self._weather_index: Dict[date, WeatherPayload] = {}
        self._decision_map: Dict[str, DecisionResult] = {}
        self._conflicts: List[ConflictRecord] = []
        self._warnings: List[str] = []
        self._farm_ctx: Optional[FarmContext] = None
        self._now: datetime = datetime.now(timezone.utc)

    # ─────────────────────────────────────────────────────────────────────────
    # PUBLIC API
    # ─────────────────────────────────────────────────────────────────────────

    def run(self, scheduler_input: SchedulerInput) -> TaskPlan:
        """
        Entry point. Runs the full scheduling pipeline and returns a TaskPlan.

        Pipeline:
            validate → score → weather_constraints → resource_constraints
            → dependencies → conflict_resolution → slot_assignment
            → enrichment → build_plan
        """
        logger.info(
            "TaskSchedulerAgent v%s starting | farm=%s | recs=%d | horizon=%dd",
            self.VERSION,
            scheduler_input.farm_context.farm_id,
            len(scheduler_input.recommendations),
            scheduler_input.planning_horizon_days,
        )

        self._reset()
        self._farm_ctx = scheduler_input.farm_context
        self._now = scheduler_input.farm_context.current_timestamp

        # Index weather by date for O(1) lookup
        for w in scheduler_input.farm_context.weather_forecast:
            self._weather_index[w.forecast_date] = w

        # 1. Validate — drop stale / malformed recommendations
        valid_recs = self._validate_recommendations(scheduler_input.recommendations)
        logger.info("Validated %d/%d recommendations", len(valid_recs), len(scheduler_input.recommendations))

        # 2. Score — compute priority_score per recommendation
        scored_recs = self._score_recommendations(valid_recs)

        # 3. Sort by score descending — highest priority first
        scored_recs.sort(key=lambda r: self._decision_map[r.recommendation_id].priority_score, reverse=True)

        # 4. Apply weather constraints
        self._apply_weather_constraints(scored_recs)

        # 5. Apply resource constraints
        self._apply_resource_constraints(scored_recs)

        # 6. Resolve task dependencies
        self._resolve_dependencies(scored_recs)

        # 7. Detect & resolve conflicts
        self._detect_and_resolve_conflicts(scored_recs)

        # 8. Assign schedule time slots
        scheduled_tasks = self._assign_schedule_slots(
            scored_recs,
            scheduler_input.planning_horizon_days,
        )

        # 9. Enrich tasks with instructions, KPIs, precautions
        if settings.ENABLE_INSTRUCTION_ENRICHMENT:
            self._enrich_tasks(scheduled_tasks)

        # 10. Build and return final plan
        plan = self._build_plan(
            scheduler_input=scheduler_input,
            scheduled_tasks=scheduled_tasks,
        )

        logger.info(
            "Plan %s complete | scheduled=%d delayed=%d skipped=%d conflicts=%d",
            plan.plan_id,
            plan.total_tasks_scheduled,
            plan.total_tasks_delayed,
            plan.total_tasks_skipped,
            len(plan.conflicts_detected),
        )
        return plan

    # ─────────────────────────────────────────────────────────────────────────
    # PIPELINE STAGES
    # ─────────────────────────────────────────────────────────────────────────

    def _reset(self) -> None:
        self._weather_index = {}
        self._decision_map = {}
        self._conflicts = []
        self._warnings = []
        self._farm_ctx = None

    # ── Stage 1: Validation ───────────────────────────────────────────────────

    def _validate_recommendations(
        self, recs: List[AgentRecommendation]
    ) -> List[AgentRecommendation]:
        """Drop stale, expired, or structurally invalid recommendations."""
        valid = []
        stale_cutoff = self._now - timedelta(hours=settings.RECOMMENDATION_STALE_HOURS)

        for rec in recs:
            # Staleness check
            if rec.generated_at.replace(tzinfo=timezone.utc) < stale_cutoff:
                logger.warning("Dropping stale recommendation %s from %s (age > %dh)",
                               rec.recommendation_id, rec.source_agent,
                               settings.RECOMMENDATION_STALE_HOURS)
                self._warnings.append(
                    f"Recommendation {rec.recommendation_id} from {rec.source_agent} "
                    f"was dropped (stale — older than {settings.RECOMMENDATION_STALE_HOURS}h)."
                )
                continue

            # Expiry check
            if rec.valid_until:
                vu = rec.valid_until
                if vu.tzinfo is None:
                    vu = vu.replace(tzinfo=timezone.utc)
                if vu < self._now:
                    logger.warning("Dropping expired recommendation %s", rec.recommendation_id)
                    self._warnings.append(
                        f"Recommendation {rec.recommendation_id} expired at {rec.valid_until.isoformat()}."
                    )
                    continue

            valid.append(rec)

        return valid

    # ── Stage 2: Scoring ──────────────────────────────────────────────────────

    def _score_recommendations(
        self, recs: List[AgentRecommendation]
    ) -> List[AgentRecommendation]:
        """
        Compute a composite priority score for each recommendation.

        Formula:
            trust_multiplier = AGENT_TRUST_MULTIPLIERS[source_agent]
            raw_score = (urgency * W_URGENCY) + (risk * W_RISK) + (impact * W_IMPACT)
            priority_score = raw_score * trust_multiplier   [clamped 0–10]
        """
        Wu = settings.PRIORITY_WEIGHT_URGENCY
        Wr = settings.PRIORITY_WEIGHT_RISK
        Wi = settings.PRIORITY_WEIGHT_IMPACT
        trust = settings.AGENT_TRUST_MULTIPLIERS

        for rec in recs:
            multiplier = trust.get(rec.source_agent.value, 1.0)
            raw = (rec.urgency_score * Wu) + (rec.risk_score * Wr) + (rec.impact_score * Wi)
            score = min(10.0, raw * multiplier)
            priority = self._score_to_priority(score)

            self._decision_map[rec.recommendation_id] = DecisionResult(
                recommendation_id=rec.recommendation_id,
                decision="execute_now",
                reason=f"Priority score {score:.2f} computed from urgency={rec.urgency_score}, "
                       f"risk={rec.risk_score}, impact={rec.impact_score} "
                       f"(trust_multiplier={multiplier}).",
                priority=priority,
                priority_score=score,
                scheduled_start=self._now,
            )
            logger.debug("Scored %s → %.2f (%s)", rec.recommendation_id, score, priority.value)

        return recs

    # ── Stage 3: Weather Constraints ─────────────────────────────────────────

    def _apply_weather_constraints(self, recs: List[AgentRecommendation]) -> None:
        """
        Delay or skip tasks based on upcoming weather forecast.

        Rules:
        - rain_probability > 70% → delay irrigation, delay pesticide
        - rain_probability > 85% → delay all outdoor sensitive tasks
        - wind_speed > 15 km/h → delay spray applications
        - frost_risk → delay sensitive planting/irrigation
        - storm_warning → delay all non-critical outdoor tasks
        - heat_stress_risk → delay labor-intensive tasks
        """
        for rec in recs:
            decision = self._decision_map[rec.recommendation_id]
            if decision.decision == "skip":
                continue

            target_date = (self._now + timedelta(hours=1)).date()
            weather = self._weather_index.get(target_date)
            if not weather:
                continue  # No forecast data → proceed as-is with a warning

            reasons: List[str] = []
            should_delay = False
            delay_until: Optional[datetime] = None

            # ── Rule: High rain probability ────────────────────────────────
            if weather.rain_probability_percent >= settings.RAIN_PROBABILITY_DELAY_THRESHOLD:
                if rec.task_category in (TaskCategory.IRRIGATION,):
                    should_delay = True
                    reasons.append(
                        f"Rain probability {weather.rain_probability_percent:.0f}% "
                        f"≥ {settings.RAIN_PROBABILITY_DELAY_THRESHOLD:.0f}% threshold — "
                        "natural precipitation may satisfy irrigation requirement."
                    )
                if rec.requires_dry_weather or rec.task_category == TaskCategory.PEST_CONTROL:
                    should_delay = True
                    reasons.append(
                        f"Task requires dry conditions; rain probability "
                        f"{weather.rain_probability_percent:.0f}% too high."
                    )

            # ── Rule: Very high rain probability ──────────────────────────
            if weather.rain_probability_percent >= settings.RAIN_PROBABILITY_SENSITIVE_THRESHOLD:
                if rec.task_category in (TaskCategory.FERTILIZATION, TaskCategory.SOIL_PREP):
                    should_delay = True
                    reasons.append(
                        f"Rain probability {weather.rain_probability_percent:.0f}% "
                        f"≥ {settings.RAIN_PROBABILITY_SENSITIVE_THRESHOLD:.0f}% — "
                        "fertilizer/amendments may leach before absorption."
                    )

            # ── Rule: High wind speed ──────────────────────────────────────
            if weather.wind_speed_kmh > settings.WIND_SPEED_SPRAY_MAX_KMH:
                if rec.task_category in (TaskCategory.PEST_CONTROL, TaskCategory.FERTILIZATION):
                    should_delay = True
                    reasons.append(
                        f"Wind speed {weather.wind_speed_kmh:.1f} km/h exceeds "
                        f"{settings.WIND_SPEED_SPRAY_MAX_KMH:.0f} km/h limit for spray applications."
                    )

            # ── Rule: Temperature extremes ─────────────────────────────────
            if rec.task_category == TaskCategory.PEST_CONTROL:
                if weather.temperature_high_c > settings.TEMP_SPRAY_MAX_C:
                    should_delay = True
                    reasons.append(
                        f"High temperature {weather.temperature_high_c:.1f}°C exceeds "
                        f"{settings.TEMP_SPRAY_MAX_C:.0f}°C spray safety limit — "
                        "chemical efficacy degrades and volatilization risk rises."
                    )
                if weather.temperature_low_c < settings.TEMP_SPRAY_MIN_C:
                    should_delay = True
                    reasons.append(
                        f"Low temperature {weather.temperature_low_c:.1f}°C below "
                        f"{settings.TEMP_SPRAY_MIN_C:.0f}°C — spray absorption will be impaired."
                    )

            # ── Rule: Frost risk ──────────────────────────────────────────
            if weather.frost_risk:
                if rec.task_category.value in settings.FROST_DELAY_CATEGORIES:
                    should_delay = True
                    reasons.append(
                        "Frost risk detected — delaying sensitive field operations "
                        "to protect crop and equipment."
                    )

            # ── Rule: Storm warning ───────────────────────────────────────
            if weather.storm_warning:
                if decision.priority not in (Priority.CRITICAL,):
                    should_delay = True
                    reasons.append(
                        "Storm warning in effect — deferring non-critical outdoor tasks "
                        "for worker and equipment safety."
                    )

            # ── Rule: Heat stress ─────────────────────────────────────────
            if weather.heat_stress_risk or weather.temperature_high_c >= settings.HEAT_STRESS_TEMP_C:
                if rec.task_category in (
                    TaskCategory.WEEDING, TaskCategory.PRUNING, TaskCategory.HARVESTING
                ):
                    should_delay = True
                    reasons.append(
                        f"Heat stress risk ({weather.temperature_high_c:.1f}°C) — "
                        "rescheduling labor-intensive tasks to morning window (before 10:00)."
                    )

            if should_delay:
                # Find earliest suitable date in forecast window
                delay_until = self._find_next_suitable_date(rec, target_date)
                decision.decision = "delay"
                decision.delay_until = delay_until
                decision.weather_constraint_applied = True
                decision.reason = (
                    f"[WEATHER CONSTRAINT] " + " | ".join(reasons) +
                    (f" → Rescheduled to {delay_until.date().isoformat()}."
                     if delay_until else " → No suitable window found in forecast horizon.")
                )
                if not delay_until:
                    decision.decision = "skip"
                    decision.skip_reason = "No weather-suitable window in planning horizon."

    def _find_next_suitable_date(
        self, rec: AgentRecommendation, start_date: date
    ) -> Optional[datetime]:
        """Scan forecast window forward to find a suitable execution date."""
        for days_ahead in range(1, settings.MAX_PLANNING_HORIZON_DAYS + 1):
            candidate = start_date + timedelta(days=days_ahead)
            weather = self._weather_index.get(candidate)
            if not weather:
                continue

            unsuitable = False

            if rec.task_category == TaskCategory.IRRIGATION:
                if weather.rain_probability_percent >= settings.RAIN_PROBABILITY_DELAY_THRESHOLD:
                    unsuitable = True

            if rec.requires_dry_weather or rec.task_category == TaskCategory.PEST_CONTROL:
                if weather.rain_probability_percent >= settings.RAIN_PROBABILITY_DELAY_THRESHOLD:
                    unsuitable = True
                if weather.wind_speed_kmh > settings.WIND_SPEED_SPRAY_MAX_KMH:
                    unsuitable = True

            if weather.frost_risk and rec.task_category.value in settings.FROST_DELAY_CATEGORIES:
                unsuitable = True

            if weather.storm_warning:
                unsuitable = True

            if not unsuitable:
                work_start = self._now.replace(
                    year=candidate.year, month=candidate.month, day=candidate.day,
                    hour=settings.DEFAULT_WORK_START_HOUR, minute=0, second=0,
                )
                return work_start

        return None

    # ── Stage 4: Resource Constraints ────────────────────────────────────────

    def _apply_resource_constraints(self, recs: List[AgentRecommendation]) -> None:
        """
        Delay or downgrade tasks when labor or water is insufficient.

        Rules:
        - No labor → delay non-critical tasks
        - Insufficient water → skip/delay irrigation tasks
        - Missing equipment → warn and delay
        """
        resources = self._farm_ctx.resources
        available_labor = resources.labor_units_available
        available_water = resources.water_available_liters * (
            1 - settings.WATER_RESERVE_BUFFER_PERCENT / 100
        )

        water_allocated = 0.0

        for rec in recs:
            decision = self._decision_map[rec.recommendation_id]
            if decision.decision == "skip":
                continue

            # ── Labor check ────────────────────────────────────────────────
            if rec.requires_labor and not resources.labor_available:
                if decision.priority != Priority.CRITICAL:
                    decision.decision = "delay"
                    decision.resource_constraint_applied = True
                    decision.reason = (
                        "[RESOURCE CONSTRAINT] No labor available. "
                        f"Task requires {rec.labor_units_required} labor unit(s). "
                        "Delaying until labor is available."
                    )
                    continue
                else:
                    self._warnings.append(
                        f"CRITICAL task {rec.recommendation_id} ({rec.title}) has no labor "
                        "assigned — farm manager must escalate immediately."
                    )

            if rec.requires_labor and rec.labor_units_required > available_labor:
                if decision.priority not in (Priority.CRITICAL, Priority.HIGH):
                    decision.decision = "delay"
                    decision.resource_constraint_applied = True
                    decision.reason = (
                        f"[RESOURCE CONSTRAINT] Task needs {rec.labor_units_required} labor units; "
                        f"only {available_labor} available. Delaying."
                    )
                    continue
                else:
                    self._warnings.append(
                        f"Task {rec.recommendation_id} needs {rec.labor_units_required} labor units "
                        f"but only {available_labor} are available. Proceeding (HIGH/CRITICAL priority)."
                    )

            # ── Water check (irrigation tasks only) ───────────────────────
            if rec.task_category == TaskCategory.IRRIGATION and rec.irrigation_payload:
                needed = rec.irrigation_payload.water_volume_liters
                if water_allocated + needed > available_water:
                    if decision.priority == Priority.CRITICAL:
                        self._warnings.append(
                            f"Insufficient water for CRITICAL irrigation task {rec.recommendation_id}. "
                            f"Need {needed:.0f}L, {available_water - water_allocated:.0f}L available."
                        )
                    else:
                        decision.decision = "delay"
                        decision.resource_constraint_applied = True
                        decision.reason = (
                            f"[RESOURCE CONSTRAINT] Insufficient water. Need {needed:.0f}L, "
                            f"only {available_water - water_allocated:.0f}L available after buffer. "
                            "Rescheduling when water supply is replenished."
                        )
                        continue
                water_allocated += needed

            # ── Equipment check ────────────────────────────────────────────
            missing_equipment = [
                eq for eq in rec.equipment_required
                if eq not in resources.equipment_available
            ]
            if missing_equipment:
                if decision.priority in (Priority.CRITICAL, Priority.HIGH):
                    self._warnings.append(
                        f"Task {rec.recommendation_id}: Missing equipment — "
                        f"{missing_equipment}. Farm manager must source urgently."
                    )
                else:
                    decision.decision = "delay"
                    decision.resource_constraint_applied = True
                    decision.reason = (
                        f"[RESOURCE CONSTRAINT] Missing equipment: {missing_equipment}. "
                        "Delaying until equipment is available."
                    )

    # ── Stage 5: Dependency Resolution ───────────────────────────────────────

    def _resolve_dependencies(self, recs: List[AgentRecommendation]) -> None:
        """
        Enforce that tasks with explicit 'depends_on' relationships are
        scheduled in the correct order with adequate gaps.
        """
        rec_map = {r.recommendation_id: r for r in recs}

        for rec in recs:
            decision = self._decision_map[rec.recommendation_id]
            if decision.decision == "skip":
                continue

            for dep_id in rec.depends_on:
                dep_decision = self._decision_map.get(dep_id)
                if dep_decision is None:
                    logger.warning(
                        "Recommendation %s depends on %s which is missing — dependency skipped.",
                        rec.recommendation_id, dep_id
                    )
                    continue

                if dep_decision.decision == "skip":
                    self._warnings.append(
                        f"Task {rec.recommendation_id} depends on {dep_id} which was skipped. "
                        "Proceeding without dependency — verify manually."
                    )
                    continue

                # Enforce category-pair gap
                dep_rec = rec_map.get(dep_id)
                if dep_rec:
                    gap_key = f"{dep_rec.task_category.value}->{rec.task_category.value}"
                    gap_hours = settings.TASK_DEPENDENCY_GAP_HOURS.get(gap_key, 0)

                    if gap_hours > 0:
                        dep_start = dep_decision.scheduled_start or self._now
                        earliest_allowed = dep_start + timedelta(
                            minutes=dep_rec.estimated_duration_minutes
                        ) + timedelta(hours=gap_hours)

                        if decision.scheduled_start and decision.scheduled_start < earliest_allowed:
                            decision.scheduled_start = earliest_allowed
                            decision.dependency_constraint_applied = True
                            decision.reason += (
                                f" | [DEPENDENCY] Must wait {gap_hours}h after "
                                f"'{dep_rec.title}' completes → rescheduled to "
                                f"{earliest_allowed.isoformat()}."
                            )
                            logger.debug(
                                "Task %s pushed to %s (dependency gap: %s → %dh)",
                                rec.recommendation_id, earliest_allowed, gap_key, gap_hours
                            )

    # ── Stage 6: Conflict Detection & Resolution ──────────────────────────────

    def _detect_and_resolve_conflicts(self, recs: List[AgentRecommendation]) -> None:
        """
        Detect conflicts:
        1. Duplicate category on same day (when not allowed)
        2. Resource over-commitment (water, labor)
        3. Mutually exclusive tasks (e.g., irrigation + pesticide within 4h)

        Resolution strategy: keep higher-priority task, delay/skip the other.
        """
        # Group active tasks by (field_id, category, date)
        buckets: Dict[Tuple, List[AgentRecommendation]] = defaultdict(list)

        for rec in recs:
            decision = self._decision_map[rec.recommendation_id]
            if decision.decision == "skip":
                continue
            bucket_date = (decision.scheduled_start or self._now).date()
            key = (rec.field_id, rec.task_category, bucket_date)
            buckets[key].append(rec)

        for (field_id, category, bucket_date), bucket_recs in buckets.items():
            if len(bucket_recs) <= 1:
                continue

            # Sort by priority score descending — keep best one
            bucket_recs.sort(
                key=lambda r: self._decision_map[r.recommendation_id].priority_score,
                reverse=True
            )
            winner = bucket_recs[0]
            losers = bucket_recs[1:]

            if not settings.ALLOW_SAME_CATEGORY_SAME_DAY:
                for loser in losers:
                    loser_decision = self._decision_map[loser.recommendation_id]
                    conflict_id = f"conflict-{uuid.uuid4().hex[:8]}"

                    # Try to push to next day
                    next_day_start = (self._now + timedelta(days=1)).replace(
                        hour=settings.DEFAULT_WORK_START_HOUR, minute=0, second=0
                    )
                    loser_decision.decision = "delay"
                    loser_decision.delay_until = next_day_start
                    loser_decision.reason = (
                        f"[CONFLICT] Same category '{category.value}' already scheduled "
                        f"for field {field_id} on {bucket_date} by task "
                        f"'{winner.title}' (score: "
                        f"{self._decision_map[winner.recommendation_id].priority_score:.2f}). "
                        f"Rescheduling to {next_day_start.date().isoformat()}."
                    )

                    self._conflicts.append(ConflictRecord(
                        conflict_id=conflict_id,
                        conflicting_recommendation_ids=[
                            winner.recommendation_id, loser.recommendation_id
                        ],
                        conflict_type=f"duplicate_category:{category.value}",
                        description=(
                            f"Two '{category.value}' tasks scheduled for field "
                            f"{field_id} on {bucket_date}."
                        ),
                        resolution=ConflictResolution.RESCHEDULE,
                        resolution_reason=(
                            f"Kept higher-priority task '{winner.title}' "
                            f"(score {self._decision_map[winner.recommendation_id].priority_score:.2f}). "
                            f"Delayed '{loser.title}' to next available day."
                        ),
                    ))
                    logger.info(
                        "Conflict resolved: %s pushed to %s (lower priority than %s)",
                        loser.recommendation_id, next_day_start.date(), winner.recommendation_id
                    )

    # ── Stage 7: Slot Assignment ──────────────────────────────────────────────

    def _assign_schedule_slots(
        self,
        recs: List[AgentRecommendation],
        horizon_days: int,
    ) -> List[ScheduledTask]:
        """
        Assign concrete start/end times to each task within working hours.
        Bin into daily slots, respecting max tasks/day and labor limits.
        """
        tasks: List[ScheduledTask] = []

        # Track slot occupancy per day: day → list of (start, end) intervals
        day_slots: Dict[date, List[Tuple[datetime, datetime]]] = defaultdict(list)
        day_task_count: Dict[date, int] = defaultdict(int)
        day_labor_minutes: Dict[date, float] = defaultdict(float)

        for rec in recs:
            decision = self._decision_map[rec.recommendation_id]

            task_id = f"task-{uuid.uuid4().hex[:10]}"

            # Determine scheduled start
            if decision.decision == "skip":
                task = self._build_skipped_task(task_id, rec, decision)
                tasks.append(task)
                continue

            if decision.decision == "delay":
                task = self._build_delayed_task(task_id, rec, decision)
                tasks.append(task)
                continue

            # Execute now / execute_now: find first available slot
            target_date = (decision.scheduled_start or self._now).date()

            # Clamp to planning horizon
            horizon_end = self._now.date() + timedelta(days=horizon_days)

            # Try to fit within horizon
            placed = False
            for offset in range(horizon_days + 1):
                candidate_date = target_date + timedelta(days=offset)
                if candidate_date > horizon_end:
                    break

                # Check daily limits
                if day_task_count[candidate_date] >= settings.MAX_TASKS_PER_DAY:
                    continue
                labor_hours = day_labor_minutes[candidate_date] / 60.0
                if labor_hours + rec.estimated_duration_minutes / 60.0 > settings.MAX_LABOR_HOURS_PER_DAY:
                    continue

                # Find first free time slot on this day
                work_start = datetime(
                    candidate_date.year, candidate_date.month, candidate_date.day,
                    settings.DEFAULT_WORK_START_HOUR, 0, 0,
                    tzinfo=timezone.utc,
                )
                work_end = datetime(
                    candidate_date.year, candidate_date.month, candidate_date.day,
                    settings.DEFAULT_WORK_END_HOUR, 0, 0,
                    tzinfo=timezone.utc,
                )

                slot_start = self._find_free_slot(
                    day_slots[candidate_date], work_start, work_end,
                    rec.estimated_duration_minutes
                )
                if slot_start is None:
                    continue

                slot_end = slot_start + timedelta(minutes=rec.estimated_duration_minutes)
                day_slots[candidate_date].append((slot_start, slot_end))
                day_task_count[candidate_date] += 1
                day_labor_minutes[candidate_date] += rec.estimated_duration_minutes

                decision.scheduled_start = slot_start
                task = self._build_scheduled_task(task_id, rec, decision, slot_start, slot_end)
                tasks.append(task)
                placed = True
                break

            if not placed:
                # Can't fit in horizon — delay beyond horizon
                decision.decision = "delay"
                decision.delay_until = self._now + timedelta(days=horizon_days + 1)
                decision.reason += (
                    " | [CAPACITY] No available slot found within planning horizon. "
                    "Pushed beyond horizon."
                )
                task = self._build_delayed_task(task_id, rec, decision)
                tasks.append(task)

        return tasks

    def _find_free_slot(
        self,
        occupied: List[Tuple[datetime, datetime]],
        work_start: datetime,
        work_end: datetime,
        duration_minutes: int,
    ) -> Optional[datetime]:
        """Return the earliest free datetime that fits the duration within working hours."""
        if not occupied:
            return work_start

        occupied_sorted = sorted(occupied, key=lambda x: x[0])
        candidate = work_start

        for (occ_start, occ_end) in occupied_sorted:
            if candidate + timedelta(minutes=duration_minutes) <= occ_start:
                return candidate
            candidate = max(candidate, occ_end)

        if candidate + timedelta(minutes=duration_minutes) <= work_end:
            return candidate

        return None

    # ── Stage 8: Enrichment ───────────────────────────────────────────────────

    def _enrich_tasks(self, tasks: List[ScheduledTask]) -> None:
        """Add instructions, KPIs, and precautions to each scheduled task."""
        for task in tasks:
            cat = task.category.value

            task.instructions = TASK_INSTRUCTIONS.get(cat, TASK_INSTRUCTIONS["other"]).copy()
            task.kpis = TASK_KPIS.get(cat, TASK_KPIS["other"]).copy()

            # Category-specific precautions
            if task.category == TaskCategory.PEST_CONTROL:
                task.precautions = [
                    "Observe all label re-entry intervals before allowing field workers back.",
                    "Store unused chemical in original container, locked secure area.",
                    "Never mix chemicals unless explicitly specified in protocol.",
                    "Report any adverse reactions or environmental incidents immediately.",
                ]
            elif task.category == TaskCategory.IRRIGATION:
                task.precautions = [
                    "Do not irrigate during rain or when soil is waterlogged.",
                    "Monitor downstream drainage to prevent runoff contamination.",
                ]
            elif task.category == TaskCategory.FERTILIZATION:
                task.precautions = [
                    "Never apply fertilizer to frozen or waterlogged soil.",
                    "Keep records for regulatory compliance.",
                    "Avoid application near water bodies.",
                ]
            else:
                task.precautions = ["Follow farm safety protocols at all times."]

    # ── Stage 9: Build Plan ───────────────────────────────────────────────────

    def _build_plan(
        self,
        scheduler_input: SchedulerInput,
        scheduled_tasks: List[ScheduledTask],
    ) -> TaskPlan:
        """Assemble the final TaskPlan from all scheduled tasks."""
        farm_id = scheduler_input.farm_context.farm_id

        # Bin tasks into daily plans
        day_buckets: Dict[date, List[ScheduledTask]] = defaultdict(list)
        for task in scheduled_tasks:
            if task.scheduled_start:
                day_buckets[task.scheduled_start.date()].append(task)
            elif task.delay_until:
                day_buckets[task.delay_until.date()].append(task)
            else:
                day_buckets[self._now.date()].append(task)

        daily_plans: List[DailyPlan] = []
        for plan_date in sorted(day_buckets.keys()):
            day_tasks = day_buckets[plan_date]
            water_req = sum(
                t.metadata.get("water_volume_liters", 0.0) for t in day_tasks
            )
            daily_plans.append(DailyPlan(
                plan_date=plan_date,
                tasks=day_tasks,
                total_labor_units_required=sum(t.assigned_labor_units for t in day_tasks),
                total_water_required_liters=water_req,
                estimated_total_duration_minutes=sum(t.estimated_duration_minutes for t in day_tasks),
                critical_tasks_count=sum(1 for t in day_tasks if t.priority == Priority.CRITICAL),
                notes=self._generate_daily_notes(plan_date, day_tasks),
            ))

        scheduled = [t for t in scheduled_tasks if t.status == TaskStatus.SCHEDULED]
        delayed = [t for t in scheduled_tasks if t.status == TaskStatus.DELAYED]
        skipped = [t for t in scheduled_tasks if t.status == TaskStatus.SKIPPED]
        critical = [t for t in scheduled_tasks if t.priority == Priority.CRITICAL]

        summary = (
            f"Scheduled {len(scheduled)} task(s) across {len(daily_plans)} day(s). "
            f"{len(delayed)} task(s) delayed, {len(skipped)} task(s) skipped. "
            f"{len(critical)} critical task(s) require immediate attention. "
            f"{len(self._conflicts)} conflict(s) resolved."
        )

        return TaskPlan(
            plan_id=f"plan-{uuid.uuid4().hex[:10]}",
            request_id=scheduler_input.request_id,
            farm_id=farm_id,
            generated_at=self._now,
            planning_horizon_days=scheduler_input.planning_horizon_days,
            daily_plans=daily_plans,
            all_tasks=scheduled_tasks,
            total_tasks_scheduled=len(scheduled),
            total_tasks_delayed=len(delayed),
            total_tasks_skipped=len(skipped),
            critical_tasks=critical,
            conflicts_detected=self._conflicts,
            execution_summary=summary,
            warnings=self._warnings,
            agent_version=self.VERSION,
        )

    # ─────────────────────────────────────────────────────────────────────────
    # TASK BUILDERS (internal helpers)
    # ─────────────────────────────────────────────────────────────────────────

    def _build_scheduled_task(
        self,
        task_id: str,
        rec: AgentRecommendation,
        decision: DecisionResult,
        slot_start: datetime,
        slot_end: datetime,
    ) -> ScheduledTask:
        water_vol = 0.0
        if rec.irrigation_payload:
            water_vol = rec.irrigation_payload.water_volume_liters

        return ScheduledTask(
            task_id=task_id,
            source_recommendation_id=rec.recommendation_id,
            source_agent=rec.source_agent,
            farm_id=rec.farm_id,
            field_id=rec.field_id,
            title=rec.title,
            description=rec.description,
            category=rec.task_category,
            status=TaskStatus.SCHEDULED,
            priority=decision.priority,
            priority_score=round(decision.priority_score, 3),
            scheduled_start=slot_start,
            scheduled_end=slot_end,
            estimated_duration_minutes=rec.estimated_duration_minutes,
            assigned_labor_units=min(
                rec.labor_units_required,
                self._farm_ctx.resources.labor_units_available
            ),
            equipment_assigned=[
                eq for eq in rec.equipment_required
                if eq in self._farm_ctx.resources.equipment_available
            ],
            decision="execute_now",
            reason=decision.reason,
            weather_constraint_applied=decision.weather_constraint_applied,
            dependency_constraint_applied=decision.dependency_constraint_applied,
            resource_constraint_applied=decision.resource_constraint_applied,
            metadata={"water_volume_liters": water_vol},
        )

    def _build_delayed_task(
        self,
        task_id: str,
        rec: AgentRecommendation,
        decision: DecisionResult,
    ) -> ScheduledTask:
        return ScheduledTask(
            task_id=task_id,
            source_recommendation_id=rec.recommendation_id,
            source_agent=rec.source_agent,
            farm_id=rec.farm_id,
            field_id=rec.field_id,
            title=rec.title,
            description=rec.description,
            category=rec.task_category,
            status=TaskStatus.DELAYED,
            priority=decision.priority,
            priority_score=round(decision.priority_score, 3),
            scheduled_start=None,
            scheduled_end=None,
            estimated_duration_minutes=rec.estimated_duration_minutes,
            assigned_labor_units=rec.labor_units_required,
            equipment_assigned=rec.equipment_required,
            decision="delay",
            reason=decision.reason,
            delay_until=decision.delay_until,
            weather_constraint_applied=decision.weather_constraint_applied,
            dependency_constraint_applied=decision.dependency_constraint_applied,
            resource_constraint_applied=decision.resource_constraint_applied,
        )

    def _build_skipped_task(
        self,
        task_id: str,
        rec: AgentRecommendation,
        decision: DecisionResult,
    ) -> ScheduledTask:
        return ScheduledTask(
            task_id=task_id,
            source_recommendation_id=rec.recommendation_id,
            source_agent=rec.source_agent,
            farm_id=rec.farm_id,
            field_id=rec.field_id,
            title=rec.title,
            description=rec.description,
            category=rec.task_category,
            status=TaskStatus.SKIPPED,
            priority=decision.priority,
            priority_score=round(decision.priority_score, 3),
            estimated_duration_minutes=rec.estimated_duration_minutes,
            assigned_labor_units=0,
            equipment_assigned=[],
            decision="skip",
            reason=decision.reason,
            skip_reason=decision.skip_reason or "Task skipped by scheduler.",
            weather_constraint_applied=decision.weather_constraint_applied,
            dependency_constraint_applied=decision.dependency_constraint_applied,
            resource_constraint_applied=decision.resource_constraint_applied,
        )

    # ─────────────────────────────────────────────────────────────────────────
    # HELPERS
    # ─────────────────────────────────────────────────────────────────────────

    def _score_to_priority(self, score: float) -> Priority:
        if score >= settings.PRIORITY_CRITICAL_THRESHOLD:
            return Priority.CRITICAL
        if score >= settings.PRIORITY_HIGH_THRESHOLD:
            return Priority.HIGH
        if score >= settings.PRIORITY_MEDIUM_THRESHOLD:
            return Priority.MEDIUM
        if score >= settings.PRIORITY_LOW_THRESHOLD:
            return Priority.LOW
        return Priority.DEFERRED

    def _generate_daily_notes(
        self, plan_date: date, tasks: List[ScheduledTask]
    ) -> List[str]:
        notes = []
        weather = self._weather_index.get(plan_date)
        if weather:
            notes.append(
                f"Weather forecast for {plan_date}: "
                f"High {weather.temperature_high_c:.0f}°C / Low {weather.temperature_low_c:.0f}°C, "
                f"Rain {weather.rain_probability_percent:.0f}% probability, "
                f"Wind {weather.wind_speed_kmh:.0f} km/h."
            )
        critical = [t for t in tasks if t.priority == Priority.CRITICAL]
        if critical:
            notes.append(
                f"⚠ {len(critical)} CRITICAL task(s) scheduled — ensure resources are ready before work start."
            )
        delayed = [t for t in tasks if t.status == TaskStatus.DELAYED]
        if delayed:
            notes.append(
                f"{len(delayed)} task(s) have been pushed to this date from earlier delays."
            )
        return notes