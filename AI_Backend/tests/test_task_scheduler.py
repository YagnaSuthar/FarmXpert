"""
Task Scheduler Agent — test suite
==================================
Plain runner, no pytest:   python -m AI_Backend.tests.test_task_scheduler

Covers the promises the agent makes to a farmer:
  * safety rules are refused, never quietly rescheduled
  * weather moves work to a day it can actually be done
  * rain is judged by amount, not by probability alone
  * jobs are ordered so one does not undo another
  * every task says what to do, what not to do, and why
  * the plan survives missing, partial and contradictory input
"""

from __future__ import annotations

import asyncio
import sys
import traceback
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List

from AI_Backend.agents.farm_operations_automation.task_scheduler.agent import TaskSchedulerAgent
from AI_Backend.agents.farm_operations_automation.task_scheduler.config import (
    CATEGORY_CONFIG,
    DEPENDENCY_GAP_HOURS,
    MAX_TASKS_PER_DAY,
    MAX_WORK_HOURS_PER_DAY,
)
from AI_Backend.agents.farm_operations_automation.task_scheduler.playbook import (
    CROP_PLAYBOOK,
    build_guidance,
    known_crops,
)

NOW = datetime(2026, 6, 15, 5, 30, tzinfo=timezone.utc)
TODAY = NOW.date()
AGENT = TaskSchedulerAgent()

PASSED: List[str] = []
FAILED: List[str] = []


# ── helpers ─────────────────────────────────────────────────────────────────

def day(offset: int) -> str:
    return (TODAY + timedelta(days=offset)).isoformat()


def forecast(offset: int, *, tmin=24.0, tmax=33.0, rain_mm=0.0, rain_pct=0.0,
             wind=8.0, frost=False, storm=False, heat=False, windows=None) -> dict:
    return {"date": day(offset), "temp_min_c": tmin, "temp_max_c": tmax,
            "rainfall_mm": rain_mm, "rain_probability_percent": rain_pct,
            "wind_speed_kmh": wind, "frost_risk": frost, "storm_warning": storm,
            "heat_stress_risk": heat, "spray_windows": windows or []}


def plan(**blocks) -> Dict[str, Any]:
    farm = {"farm_id": "F1", "field_id": "P1", "current_timestamp": NOW.isoformat()}
    farm.update(blocks.pop("farm", {}))
    payload = {"request_id": "req-1", "farm": farm,
               "planning_horizon_days": blocks.pop("horizon", 3)}
    if "resources" in blocks:
        payload["resources"] = blocks.pop("resources")
    payload.update(blocks)
    return asyncio.run(AGENT.run(payload))


def irrigation(offset=0, *, mm=30.0, moisture=None, method="drip", hours=2.0) -> dict:
    block: Dict[str, Any] = {"schedule": [{
        "date": day(offset), "irrigation_required": True, "water_depth_mm": mm,
        "duration_hours": hours, "method": method, "timing": "morning"}]}
    if moisture is not None:
        block["soil_moisture_current_percent"] = moisture
    return block


def pest(**kw) -> dict:
    base = {"threat_detected": True, "threat_type": "leaf_spot", "severity": 7.0,
            "affected_area_percent": 25.0, "treatment_type": "fungicide",
            "chemical_name": "mancozeb", "requires_dry_conditions": True}
    base.update(kw)
    return base


def fertilizer(**kw) -> dict:
    rec = {"fertilizer": "urea", "display_name": "Urea 46-0-0", "dosage": "60 kg/ha",
           "timing": "top dressing", "method": "soil_application_with_irrigation",
           "triggered_by": "LOW_NITROGEN"}
    rec.update(kw)
    return {"fertilizers": [rec],
            "alerts": [{"type": "LOW_NITROGEN", "message": "Nitrogen is low.", "severity": "high"}]}


def tasks_of(result: dict, category: str) -> List[dict]:
    return [t for t in result["all_tasks"] if t["category"] == category]


def check(name: str, condition: Any, detail: str = "") -> None:
    if condition:
        PASSED.append(name)
    else:
        FAILED.append(f"{name}: {detail}" if detail else name)


def case(fn):
    try:
        fn()
    except Exception:  # noqa: BLE001
        FAILED.append(f"{fn.__name__} raised:\n{traceback.format_exc()}")
    return fn


# ── 1. Food safety and human safety ─────────────────────────────────────────

@case
def test_pre_harvest_interval_refused():
    """A spray inside the pre-harvest interval is refused, not rescheduled."""
    result = plan(farm={"days_to_harvest": 3, "current_crop": "tomato"},
                  pest_disease_agent=pest(pre_harvest_interval_days=14))
    check("PHI refuses the spray", len(result["refused_tasks"]) == 1, result["refused_tasks"])
    check("PHI produces no pest task", not tasks_of(result, "pest_control"))
    refusal = result["refused_tasks"][0]
    check("PHI refusal names the rule", "14" in refusal["rule"])
    check("PHI refusal explains residue", "residue" in refusal["explanation"].lower())
    check("PHI refusal offers an alternative", bool(refusal["what_to_do_instead"]))
    check("PHI refusal leads the headline", "not safe" in result["headline"].lower())


@case
def test_pre_harvest_interval_allows_safe_spray():
    result = plan(farm={"days_to_harvest": 30},
                  pest_disease_agent=pest(pre_harvest_interval_days=14))
    check("spray outside PHI is allowed", len(tasks_of(result, "pest_control")) == 1)
    check("no refusal outside PHI", not result["refused_tasks"])


@case
def test_default_phi_applies_when_label_unknown():
    """No PHI given means the conservative default, not 'no limit'."""
    result = plan(farm={"days_to_harvest": 2}, pest_disease_agent=pest())
    check("unknown PHI still protects harvest", len(result["refused_tasks"]) == 1)


@case
def test_bee_toxic_spray_on_flowering_crop_refused():
    result = plan(farm={"in_flower": True, "current_crop": "mustard"},
                  pest_disease_agent=pest(bee_toxic=True))
    check("bee-toxic spray refused in flower", len(result["refused_tasks"]) == 1)
    check("bee refusal explains pollination",
          "bee" in result["refused_tasks"][0]["explanation"].lower())
    result_ok = plan(farm={"in_flower": False}, pest_disease_agent=pest(bee_toxic=True))
    check("bee-toxic spray fine outside flowering", not result_ok["refused_tasks"])


@case
def test_spray_task_carries_re_entry_and_phi():
    result = plan(farm={"days_to_harvest": 60},
                  pest_disease_agent=pest(pre_harvest_interval_days=10, re_entry_interval_hours=48))
    task = tasks_of(result, "pest_control")[0]
    joined = " ".join(task["safety"])
    check("re-entry interval is stated", "48 hours" in joined, joined)
    check("PHI is stated on the task", "10 day" in joined, joined)
    check("protective equipment is stated", "gloves" in joined.lower())


# ── 2. Weather: amounts, not probabilities ──────────────────────────────────

@case
def test_light_rain_does_not_cancel_irrigation():
    """70 % chance of 2 mm does not replace a 30 mm irrigation."""
    result = plan(irrigation_agent=irrigation(mm=30),
                  weather_agent={"forecast": [forecast(0, rain_mm=2.0, rain_pct=70.0)]})
    task = tasks_of(result, "irrigation")[0]
    check("light rain keeps irrigation today", task["scheduled_date"] == day(0),
          f"landed {task['scheduled_date']}")


@case
def test_heavy_rain_replaces_irrigation():
    result = plan(irrigation_agent=irrigation(mm=30),
                  weather_agent={"forecast": [forecast(0, rain_mm=40.0, rain_pct=90.0),
                                              forecast(1), forecast(2)]})
    task = tasks_of(result, "irrigation")[0]
    check("heavy rain moves irrigation off today", task["scheduled_date"] != day(0))
    check("rain reason is in millimetres",
          any("mm" in b for b in task["blocked_by"]), task["blocked_by"])


@case
def test_big_rain_chance_but_small_amount_is_ignored():
    """The forecast must mean something: 95 % chance of 0.4 mm is a dry day."""
    result = plan(irrigation_agent=irrigation(mm=25),
                  weather_agent={"forecast": [forecast(0, rain_mm=0.4, rain_pct=95.0)]})
    check("trace rain is not a blocker", tasks_of(result, "irrigation")[0]["blocked_by"] == [])


@case
def test_low_confidence_forecast_is_ignored():
    """30 % chance of 50 mm is not a reason to cancel today's work."""
    result = plan(irrigation_agent=irrigation(mm=25),
                  weather_agent={"forecast": [forecast(0, rain_mm=50.0, rain_pct=30.0)]})
    check("unlikely rain does not move work",
          tasks_of(result, "irrigation")[0]["scheduled_date"] == day(0))


@case
def test_wind_blocks_spraying_but_not_irrigation():
    windy = {"forecast": [forecast(0, wind=30.0), forecast(1), forecast(2)]}
    sprayed = plan(farm={"days_to_harvest": 60}, pest_disease_agent=pest(), weather_agent=windy)
    spray_task = tasks_of(sprayed, "pest_control")[0]
    check("wind moves the spray", spray_task["scheduled_date"] != day(0))
    check("wind reason is stated in km/h",
          any("km/h" in b for b in spray_task["blocked_by"]), spray_task["blocked_by"])

    watered = plan(irrigation_agent=irrigation(), weather_agent=windy)
    check("wind does not block drip irrigation",
          tasks_of(watered, "irrigation")[0]["scheduled_date"] == day(0))


@case
def test_hot_day_still_allows_a_morning_spray():
    """A 36 C afternoon does not waste the 26 C morning."""
    result = plan(farm={"days_to_harvest": 60}, pest_disease_agent=pest(),
                  weather_agent={"forecast": [forecast(0, tmin=26.0, tmax=36.0)]})
    task = tasks_of(result, "pest_control")[0]
    check("hot afternoon keeps the spray today", task["scheduled_date"] == day(0))
    check("spray is booked in the morning", task["scheduled_start_time"] < "11:00",
          task["scheduled_start_time"])


@case
def test_night_that_never_cools_blocks_the_spray():
    result = plan(farm={"days_to_harvest": 60}, pest_disease_agent=pest(),
                  weather_agent={"forecast": [forecast(0, tmin=33.0, tmax=44.0),
                                              forecast(1), forecast(2)]})
    check("a day hot from dawn moves the spray",
          tasks_of(result, "pest_control")[0]["scheduled_date"] != day(0))


@case
def test_weather_agent_spray_windows_are_trusted():
    """When the Weather Watcher has found hourly windows, they win."""
    result = plan(farm={"days_to_harvest": 60}, pest_disease_agent=pest(),
                  weather_agent={"forecast": [forecast(0, wind=30.0, windows=["06:00-08:00"])]})
    check("hourly windows override the daily wind average",
          tasks_of(result, "pest_control")[0]["scheduled_date"] == day(0))


@case
def test_frozen_ground_blocks_irrigation():
    result = plan(irrigation_agent=irrigation(),
                  weather_agent={"forecast": [forecast(0, tmin=-3.0, tmax=1.0),
                                              forecast(1, tmin=-2.0, tmax=1.5),
                                              forecast(2, tmin=-2.0, tmax=1.0),
                                              forecast(3, tmin=-3.0, tmax=0.5)]})
    task = tasks_of(result, "irrigation")[0]
    check("frozen ground stops irrigation entirely", task["status"] == "skipped", task["status"])
    check("frozen reason is explained",
          "frozen" in (task["skip_reason"] or "").lower(), task["skip_reason"])


@case
def test_frost_blocks_planting():
    result = plan(farm={"current_crop": None},
                  crop_selector_agent={"recommended_crops": [
                      {"crop_name": "maize", "suitability_score": 8.0}]},
                  weather_agent={"forecast": [forecast(0, tmin=1.0, frost=True), forecast(1),
                                              forecast(2), forecast(3)]})
    sowing = tasks_of(result, "planting")
    check("frost moves sowing", sowing and sowing[0]["scheduled_date"] != day(0))


@case
def test_gale_stops_open_field_work():
    result = plan(irrigation_agent=irrigation(method="sprinkler"),
                  weather_agent={"forecast": [forecast(0, wind=70.0), forecast(1)]})
    task = tasks_of(result, "irrigation")[0]
    check("gale moves the work", task["scheduled_date"] != day(0))
    check("gale reason mentions safety",
          any("unsafe" in b for b in task["blocked_by"]), task["blocked_by"])


@case
def test_wet_field_blocks_machinery():
    result = plan(farm={"current_crop": None},
                  crop_selector_agent={"recommended_crops": [
                      {"crop_name": "wheat", "suitability_score": 8.0}]},
                  weather_agent={"forecast": [forecast(0, rain_mm=30.0, rain_pct=90.0),
                                              forecast(1), forecast(2), forecast(3)]})
    prep = tasks_of(result, "soil_preparation")
    check("wet field moves land preparation", prep and prep[0]["scheduled_date"] != day(0))


@case
def test_heavy_rain_moves_fertilizer_but_light_rain_does_not():
    heavy = plan(soil_health_agent=fertilizer(),
                 weather_agent={"forecast": [forecast(0, rain_mm=40.0, rain_pct=90.0),
                                             forecast(1), forecast(2)]})
    check("leaching rain moves fertilizer",
          tasks_of(heavy, "fertilization")[0]["scheduled_date"] != day(0))
    light = plan(soil_health_agent=fertilizer(),
                 weather_agent={"forecast": [forecast(0, rain_mm=6.0, rain_pct=80.0)]})
    check("a light shower does not move fertilizer",
          tasks_of(light, "fertilization")[0]["scheduled_date"] == day(0))


@case
def test_no_weather_data_still_plans():
    result = plan(irrigation_agent=irrigation(moisture=20))
    check("plan works with no forecast", result["total_tasks_scheduled"] >= 1)
    check("nothing is falsely weather-blocked",
          all(not t["weather_constraint_applied"] for t in result["all_tasks"]))


# ── 3. Ordering between jobs ────────────────────────────────────────────────

@case
def test_irrigation_waits_after_spraying():
    result = plan(farm={"days_to_harvest": 60},
                  pest_disease_agent=pest(),
                  irrigation_agent=irrigation(mm=20),
                  horizon=5)
    spray = tasks_of(result, "pest_control")[0]
    water = tasks_of(result, "irrigation")[0]
    gap_hours = DEPENDENCY_GAP_HOURS["pest_control->irrigation"]
    spray_day = date.fromisoformat(spray["scheduled_date"])
    water_day = date.fromisoformat(water["scheduled_date"])
    check("water comes at least a day after the spray",
          (water_day - spray_day).days >= gap_hours / 24.0,
          f"spray {spray_day}, water {water_day}")
    check("the wait is explained to the farmer",
          bool(water["blocked_by"]) or water_day > spray_day)


@case
def test_sowing_follows_land_preparation():
    result = plan(farm={"current_crop": None},
                  crop_selector_agent={"recommended_crops": [
                      {"crop_name": "maize", "suitability_score": 8.5}]},
                  horizon=5)
    prep = tasks_of(result, "soil_preparation")[0]
    sow = tasks_of(result, "planting")[0]
    check("sowing is after land preparation",
          sow["scheduled_date"] > prep["scheduled_date"],
          f"prep {prep['scheduled_date']}, sow {sow['scheduled_date']}")


@case
def test_two_jobs_never_overlap_in_time():
    result = plan(farm={"days_to_harvest": 60},
                  pest_disease_agent=pest(),
                  soil_health_agent=fertilizer(),
                  irrigation_agent=irrigation(mm=10),
                  horizon=5)
    by_day: Dict[str, List[dict]] = {}
    for t in result["all_tasks"]:
        if t["status"] == "scheduled":
            by_day.setdefault(t["scheduled_date"], []).append(t)
    overlaps = []
    for when, group in by_day.items():
        group.sort(key=lambda t: t["scheduled_start_time"])
        for earlier, later in zip(group, group[1:]):
            if later["scheduled_start_time"] < earlier["scheduled_end_time"]:
                overlaps.append((when, earlier["title"], later["title"]))
    check("no two jobs are booked at the same time", not overlaps, overlaps)


@case
def test_start_times_are_readable():
    result = plan(irrigation_agent=irrigation(hours=1.3))
    for t in result["all_tasks"]:
        if t["scheduled_start_time"]:
            minute = int(t["scheduled_start_time"].split(":")[1])
            check("start times land on a quarter hour", minute % 15 == 0,
                  t["scheduled_start_time"])


@case
def test_nothing_is_scheduled_in_the_past():
    late = datetime(2026, 6, 15, 16, 0, tzinfo=timezone.utc)
    result = asyncio.run(AGENT.run({
        "request_id": "r", "farm": {"farm_id": "F", "field_id": "P",
                                    "current_timestamp": late.isoformat()},
        "irrigation_agent": irrigation(mm=10)}))
    for t in result["all_tasks"]:
        if t["status"] == "scheduled" and t["scheduled_date"] == day(0):
            check("today's work starts after the current hour",
                  t["scheduled_start_time"] >= "16:00", t["scheduled_start_time"])


# ── 4. Resources ────────────────────────────────────────────────────────────

@case
def test_missing_water_delays_routine_irrigation():
    result = plan(irrigation_agent=irrigation(mm=50),
                  farm={"total_area_hectares": 5.0},
                  resources={"labor_units_available": 2, "water_available_liters": 1000.0})
    task = tasks_of(result, "irrigation")[0]
    check("not enough water delays the job", task["status"] == "delayed", task["status"])
    check("the shortfall is quantified",
          any("litre" in b for b in task["blocked_by"]), task["blocked_by"])


@case
def test_critical_irrigation_warns_instead_of_failing_silently():
    result = plan(irrigation_agent=irrigation(mm=50, moisture=15),
                  farm={"total_area_hectares": 5.0, "growth_stage": "flowering"},
                  resources={"labor_units_available": 2, "water_available_liters": 1000.0})
    check("critical irrigation is not silently dropped",
          any("litres" in w for w in result["warnings"]), result["warnings"])
    check("the advice is to prioritise part of the field",
          any("first" in w for w in result["warnings"]), result["warnings"])


@case
def test_not_enough_people_delays_routine_work():
    result = plan(farm={"current_crop": None},
                  crop_selector_agent={"recommended_crops": [
                      {"crop_name": "maize", "suitability_score": 8.0}]},
                  resources={"labor_units_available": 1})
    prep = tasks_of(result, "soil_preparation")[0]
    check("a one-person farm delays a two-person job", prep["status"] == "delayed", prep["status"])
    check("the reason names the shortfall",
          any("people" in b for b in prep["blocked_by"]), prep["blocked_by"])


@case
def test_day_is_never_overloaded():
    schedule = [{"date": day(0), "irrigation_required": True, "water_depth_mm": 5,
                 "duration_hours": 3, "method": "flood", "timing": "morning",
                 "reason": f"block {i}"} for i in range(6)]
    result = plan(irrigation_agent={"schedule": schedule},
                  resources={"labor_units_available": 5, "water_available_liters": 10_000_000},
                  horizon=5)
    per_day: Dict[str, float] = {}
    counts: Dict[str, int] = {}
    for t in result["all_tasks"]:
        if t["status"] == "scheduled":
            per_day[t["scheduled_date"]] = per_day.get(t["scheduled_date"], 0) + t["duration_minutes"]
            counts[t["scheduled_date"]] = counts.get(t["scheduled_date"], 0) + 1
    check("no day exceeds the work-hour limit",
          all(v / 60.0 <= MAX_WORK_HOURS_PER_DAY for v in per_day.values()), per_day)
    check("no day exceeds the task limit",
          all(v <= MAX_TASKS_PER_DAY for v in counts.values()), counts)


@case
def test_equipment_check_only_applies_when_the_farm_listed_any():
    unlisted = plan(farm={"days_to_harvest": 60}, pest_disease_agent=pest())
    check("an unanswered equipment list does not block work",
          tasks_of(unlisted, "pest_control")[0]["status"] == "scheduled")
    listed = plan(farm={"days_to_harvest": 60}, pest_disease_agent=pest(severity=3.0),
                  resources={"equipment_available": ["tractor"]})
    task = tasks_of(listed, "pest_control")[0]
    check("a missing sprayer is noticed",
          task["status"] == "delayed" or any("sprayer" in w for w in listed["warnings"]),
          task["status"])


# ── 5. Guidance: what to do and what not to do ──────────────────────────────

@case
def test_every_task_carries_guidance():
    result = plan(farm={"days_to_harvest": 60, "current_crop": "groundnut"},
                  pest_disease_agent=pest(),
                  soil_health_agent=fertilizer(),
                  irrigation_agent=irrigation(mm=20),
                  horizon=5)
    for t in result["all_tasks"]:
        check(f"{t['category']} says what to do", len(t["do"]) >= 2, t["title"])
        check(f"{t['category']} says what not to do", len(t["do_not"]) >= 1, t["title"])
        check(f"{t['category']} explains why now", len(t["why_now"]) > 20, t["title"])


@case
def test_every_dont_carries_its_reason():
    """A rule without a reason is a rule a farmer ignores."""
    for category in CATEGORY_CONFIG:
        guidance = build_guidance(category)
        for line in guidance["do_not"]:
            has_reason = any(word in line.lower() for word in
                             (" - ", "because", "; ", "invite", "costs", "loses", "lost",
                              "burns", "kills", "makes", "wash", "runs off", "cannot",
                              "drift", "do not recover", "sets the lowest", "resistant"))
            check(f"{category} explains its don't", has_reason, line)


@case
def test_crop_specific_advice_comes_first():
    result = plan(farm={"current_crop": "groundnut", "growth_stage": "pegging"},
                  irrigation_agent=irrigation(mm=25))
    task = tasks_of(result, "irrigation")[0]
    check("groundnut advice appears", any("pegging" in d.lower() for d in task["do"]), task["do"][:2])
    check("crop advice is first", "pegging" in task["do"][0].lower(), task["do"][0])


@case
def test_unknown_crop_still_gets_general_advice():
    result = plan(farm={"current_crop": "dragonfruit"}, irrigation_agent=irrigation())
    task = tasks_of(result, "irrigation")[0]
    check("unknown crop keeps general advice", len(task["do"]) >= 3)
    check("no crop advice is invented", not any("dragonfruit" in d.lower() for d in task["do"]))


@case
def test_crop_playbook_categories_are_real():
    for crop, categories in CROP_PLAYBOOK.items():
        for category in categories:
            check(f"{crop} advice targets a real task type", category in CATEGORY_CONFIG,
                  f"{crop} -> {category}")


@case
def test_heat_adds_a_safety_note():
    result = plan(farm={"days_to_harvest": 60}, pest_disease_agent=pest(),
                  weather_agent={"forecast": [forecast(0, tmin=28.0, tmax=41.0)]})
    task = tasks_of(result, "pest_control")[0]
    check("heat adds a warning for the person working",
          any("water" in s.lower() or "cool" in s.lower() for s in task["safety"]), task["safety"])


@case
def test_delay_states_what_waiting_costs():
    result = plan(farm={"days_to_harvest": 60}, pest_disease_agent=pest(),
                  weather_agent={"forecast": [forecast(0, wind=40.0), forecast(1, wind=40.0),
                                              forecast(2)]})
    task = tasks_of(result, "pest_control")[0]
    check("a delayed spray states the cost of waiting", bool(task["cost_of_delay"]),
          task["cost_of_delay"])
    check("the cost mentions spread",
          "spread" in (task["cost_of_delay"] or "").lower(), task["cost_of_delay"])


@case
def test_plan_has_a_headline_and_a_first_job():
    result = plan(farm={"days_to_harvest": 60}, pest_disease_agent=pest(),
                  irrigation_agent=irrigation(moisture=20))
    check("the plan has a headline", len(result["headline"]) > 15, result["headline"])
    check("the plan names a first job", bool(result["do_first"]))
    check("the first job is the highest priority",
          result["do_first"] == max(result["all_tasks"],
                                    key=lambda t: t["priority_score"])["title"])


@case
def test_quiet_day_says_so_plainly():
    result = plan(weather_agent={"forecast": [forecast(0)], "alerts": []})
    check("a quiet day is stated, not left blank", "nothing" in result["headline"].lower(),
          result["headline"])


# ── 6. Priorities ───────────────────────────────────────────────────────────

@case
def test_water_stress_at_flowering_outranks_routine_fertilizer():
    result = plan(farm={"growth_stage": "flowering", "current_crop": "maize"},
                  irrigation_agent=irrigation(moisture=18),
                  soil_health_agent=fertilizer(
                      **{"triggered_by": "LOW_NITROGEN"}))
    water = tasks_of(result, "irrigation")[0]
    fert = tasks_of(result, "fertilization")[0]
    check("critical-stage water outranks fertilizer",
          water["priority_score"] > fert["priority_score"],
          f"{water['priority_score']} vs {fert['priority_score']}")


@case
def test_severe_pest_becomes_critical():
    result = plan(farm={"days_to_harvest": 60},
                  pest_disease_agent=pest(severity=9.5, affected_area_percent=70))
    check("a severe outbreak is critical",
          tasks_of(result, "pest_control")[0]["priority"] == "critical")


@case
def test_low_severity_weather_advisory_is_not_a_task():
    result = plan(weather_agent={"forecast": [forecast(0)], "alerts": [
        {"type": "light_breeze", "severity": "low", "message": "Breezy."}]})
    check("low-severity advisories do not become jobs", not result["all_tasks"])


@case
def test_market_is_informational_unless_an_action_is_given():
    quiet = plan(market_intelligence_agent={"commodity": "wheat",
                                            "current_modal_price_per_quintal": 2200})
    check("market data alone makes no task", not tasks_of(quiet, "market_action"))
    acting = plan(market_intelligence_agent={"commodity": "wheat", "recommended_action": "SELL_NOW",
                                             "current_modal_price_per_quintal": 2200})
    check("an explicit sell action makes a task", len(tasks_of(acting, "market_action")) == 1)


# ── 7. Odd and hostile input ────────────────────────────────────────────────

@case
def test_duplicate_recommendations_are_merged():
    same = irrigation(mm=20)
    same["schedule"].append(dict(same["schedule"][0]))
    result = plan(irrigation_agent=same)
    scheduled = [t for t in tasks_of(result, "irrigation") if t["status"] == "scheduled"]
    check("the same job is not listed twice", len(scheduled) == 1, len(scheduled))
    check("the merge is recorded", len(result["conflicts_detected"]) == 1)


@case
def test_past_dated_recommendation_is_pulled_to_today():
    result = plan(irrigation_agent=irrigation(offset=-5, mm=20))
    task = tasks_of(result, "irrigation")[0]
    check("yesterday's advice is not scheduled in the past",
          task["scheduled_date"] >= day(0), task["scheduled_date"])


@case
def test_irrigation_not_required_creates_nothing():
    result = plan(irrigation_agent={"schedule": [
        {"date": day(0), "irrigation_required": False, "method": "drip"}]})
    check("a 'no irrigation needed' day makes no task", not tasks_of(result, "irrigation"))


@case
def test_empty_and_partial_blocks_are_survivable():
    for label, blocks in [
        ("weather only", {"weather_agent": {"forecast": [forecast(0)]}}),
        ("empty forecast", {"weather_agent": {"forecast": []}}),
        ("pest with no threat", {"pest_disease_agent": {"threat_detected": False}}),
        ("soil with no fertilizer", {"soil_health_agent": {"alerts": [], "fertilizers": []}}),
        ("crop with no recommendation", {"crop_selector_agent": {"recommended_crops": []}}),
    ]:
        result = plan(**blocks)
        check(f"{label} produces a valid plan", isinstance(result.get("all_tasks"), list))
        check(f"{label} still has a headline", bool(result["headline"]))


@case
def test_input_with_no_agent_block_is_rejected_clearly():
    try:
        asyncio.run(AGENT.run({"request_id": "r", "farm": {
            "farm_id": "F", "field_id": "P", "current_timestamp": NOW.isoformat()}}))
        check("a payload with no agent data is rejected", False, "no error raised")
    except Exception as exc:  # noqa: BLE001
        check("a payload with no agent data is rejected", True)
        check("the rejection explains itself", "agent data" in str(exc).lower(), str(exc)[:120])


@case
def test_langgraph_node_never_raises():
    node_result = asyncio.run(AGENT({"garbage": True}))
    check("bad state returns no update instead of crashing", node_result == {}, node_result)
    good = asyncio.run(AGENT({
        "request_id": "r",
        "farm": {"farm_id": "F", "field_id": "P", "current_timestamp": NOW.isoformat()},
        "irrigation_agent": irrigation(mm=15)}))
    check("valid state returns a plan under task_plan", "task_plan" in good)


@case
def test_orchestrator_state_shape_is_accepted():
    """Raw agent outputs under their own keys, the way the graph carries them."""
    state = {
        "farm_id": "F9", "field_id": "P9", "current_crop": "wheat",
        "current_timestamp": NOW.isoformat(),
        "irrigation_agent": irrigation(mm=20),
    }
    result = asyncio.run(AGENT.run(state))
    check("flat orchestrator state is accepted", result["farm_id"] == "F9")
    check("field id defaults sensibly", result["field_id"] == "P9")


@case
def test_horizon_is_clamped_not_rejected():
    result = plan(irrigation_agent=irrigation(), horizon=999)
    check("an absurd horizon is clamped", result["planning_horizon_days"] <= 14,
          result["planning_horizon_days"])


@case
def test_plan_is_json_safe():
    import json
    result = plan(farm={"days_to_harvest": 60, "current_crop": "cotton"},
                  pest_disease_agent=pest(), irrigation_agent=irrigation(),
                  soil_health_agent=fertilizer())
    text = json.dumps(result)
    check("the whole plan serialises to JSON", len(text) > 500)


@case
def test_same_input_gives_the_same_plan():
    blocks = dict(farm={"days_to_harvest": 60, "current_crop": "cotton"},
                  pest_disease_agent=pest(), irrigation_agent=irrigation(mm=20))
    first, second = plan(**blocks), plan(**blocks)

    def shape(result):
        return [(t["title"], t["scheduled_date"], t["scheduled_start_time"], t["status"])
                for t in result["all_tasks"]]
    check("planning is deterministic", shape(first) == shape(second))


@case
def test_daily_totals_match_the_tasks():
    result = plan(farm={"days_to_harvest": 60}, pest_disease_agent=pest(),
                  irrigation_agent=irrigation(mm=20), soil_health_agent=fertilizer(),
                  horizon=5)
    for daily in result["daily_plans"]:
        check("the day's task count matches its list",
              daily["total_tasks"] == len(daily["tasks"]))
        check("the day's work minutes match its list",
              daily["estimated_total_duration_minutes"]
              == sum(t["duration_minutes"] for t in daily["tasks"]))
        check("the day's water total matches its list",
              abs(daily["total_water_liters"]
                  - sum(t["resources_required"]["water_liters"] for t in daily["tasks"])) < 0.01)


@case
def test_counts_add_up():
    result = plan(farm={"days_to_harvest": 60}, pest_disease_agent=pest(),
                  irrigation_agent=irrigation(mm=20), soil_health_agent=fertilizer())
    total = (result["total_tasks_scheduled"] + result["total_tasks_delayed"]
             + result["total_tasks_skipped"])
    check("every task is counted exactly once", total == len(result["all_tasks"]),
          f"{total} vs {len(result['all_tasks'])}")


# ── 8. Whole-farm sweep ─────────────────────────────────────────────────────

@case
def test_many_farm_situations_produce_a_sound_plan():
    """Every combination of crop, stage, weather and resources must hold the
    same invariants: nothing in the past, nothing overlapping, no unsafe
    spray, and guidance on every task."""
    crops = known_crops() + ["dragonfruit", ""]
    stages = ["seedling", "vegetative", "flowering", "fruiting", "harvest_ready"]
    weathers = [
        [forecast(i) for i in range(4)],
        [forecast(i, rain_mm=60.0, rain_pct=95.0) for i in range(4)],
        [forecast(i, tmin=-4.0, tmax=1.0) for i in range(4)],
        [forecast(i, tmin=30.0, tmax=45.0, heat=True) for i in range(4)],
        [forecast(i, wind=70.0) for i in range(4)],
        [],
    ]
    resources = [
        {"labor_units_available": 0, "water_available_liters": 0.0},
        {"labor_units_available": 2, "water_available_liters": 50_000.0},
        {"labor_units_available": 10, "water_available_liters": 5_000_000.0},
    ]
    harvests = [None, 2, 20, 120]

    runs = 0
    problems: List[str] = []
    for crop in crops:
        for stage in stages:
            for weather in weathers:
                for res in resources:
                    for days_out in harvests:
                        runs += 1
                        result = plan(
                            farm={"current_crop": crop or None, "growth_stage": stage,
                                  "days_to_harvest": days_out, "total_area_hectares": 2.0,
                                  "in_flower": stage == "flowering"},
                            resources=res,
                            weather_agent={"forecast": weather},
                            irrigation_agent=irrigation(mm=25, moisture=20),
                            soil_health_agent=fertilizer(),
                            pest_disease_agent=pest(severity=8.0, pre_harvest_interval_days=14),
                            horizon=4)

                        where = f"{crop or 'no crop'}/{stage}/harvest={days_out}"
                        for t in result["all_tasks"]:
                            if t["status"] == "scheduled":
                                if t["scheduled_date"] < day(0):
                                    problems.append(f"{where}: '{t['title']}' in the past")
                                if not t["do"] or not t["why_now"]:
                                    problems.append(f"{where}: '{t['title']}' has no guidance")
                                if not t["scheduled_start_time"]:
                                    problems.append(f"{where}: '{t['title']}' has no time")
                            if t["status"] == "delayed" and not t["blocked_by"]:
                                problems.append(f"{where}: '{t['title']}' delayed with no reason")

                        if days_out is not None and days_out < 14:
                            if tasks_of(result, "pest_control"):
                                problems.append(f"{where}: spray allowed inside the PHI")

                        by_day: Dict[str, List[dict]] = {}
                        for t in result["all_tasks"]:
                            if t["status"] == "scheduled":
                                by_day.setdefault(t["scheduled_date"], []).append(t)
                        for when, group in by_day.items():
                            group.sort(key=lambda t: t["scheduled_start_time"])
                            for a, b in zip(group, group[1:]):
                                if b["scheduled_start_time"] < a["scheduled_end_time"]:
                                    problems.append(f"{where}: overlap on {when}")

    check(f"{runs} farm situations hold every invariant", not problems, problems[:8])
    print(f"    swept {runs} farm situations")


# ── runner ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print(f"\n{len(PASSED) + len(FAILED)} checks\n")
    for failure in FAILED:
        print("  FAIL", failure)
    print(f"\n{len(PASSED)}/{len(PASSED) + len(FAILED)} checks passed\n")
    sys.exit(1 if FAILED else 0)
