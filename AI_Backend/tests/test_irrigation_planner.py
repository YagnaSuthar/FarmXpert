"""Regression suite for the Irrigation Planner agent.

Weather is supplied directly (`weather_data`), so this runs offline and every
day's rain, temperature and ET0 is known - the right decision can be worked
out by hand.

    python -m AI_Backend.tests.test_irrigation_planner
"""
from __future__ import annotations

import asyncio
import logging
import sys
from datetime import date

from AI_Backend.agents.crop_planning_growth.irrigation_planner import water_balance as wb
from AI_Backend.agents.crop_planning_growth.irrigation_planner.agent import IrrigationAgent
from AI_Backend.agents.crop_planning_growth.irrigation_planner.config import (
    CROP_CONFIG, EMERGENCY_DEPLETION, SOIL_CONFIG)
from AI_Backend.agents.crop_planning_growth.irrigation_planner.schemas import (
    IrrigationPlannerResponse)

AGENT = IrrigationAgent()
LOCATION = {"lat": 23.02, "lon": 72.57}


def forecast(days=7, rain=None, pop=None, et0=5.0, tmin=25.0, tmax=34.0, wind=10.0):
    """`rain` / `pop` map day index -> value; other days are dry."""
    out = []
    for i in range(days):
        out.append({"date": date(2026, 9, 22 + i).isoformat(), "temp_min": tmin,
                    "temp_max": tmax, "rainfall_mm": (rain or {}).get(i, 0.0),
                    "rain_probability_percent": (pop or {}).get(i, 5.0),
                    "humidity": 60.0, "wind_speed": wind,
                    "et0_mm": et0 if et0 is not None else None})
    return {"location": LOCATION, "forecast_short_term": out, "alerts": [], "warnings": []}


async def plan(**kw):
    kw.setdefault("weather_data", forecast())
    return await AGENT.run(kw)


def first(p):
    return p["irrigation_schedule"][0]


# ---------------------------------------------------------------------------
# FAO-56 physics against published values
# ---------------------------------------------------------------------------
def case_extraterrestrial_radiation_matches_fao_example_8():
    return abs(wb.extraterrestrial_radiation(-20.0, date(2026, 9, 3)) - 32.2) < 0.1


def case_taw_and_p_adjustment():
    # Vertisol 0.40/0.22 over 0.75 m: TAW = 1000 * 0.18 * 0.75 = 135 mm.
    # p 0.50 at ETc 8 mm/d -> 0.50 + 0.04*(5-8) = 0.38 (FAO-56 Table 22 note).
    return (abs(wb.total_available_water(0.40, 0.22, 0.75) - 135.0) < 1e-9
            and abs(wb.depletion_fraction(0.50, 8.0) - 0.38) < 1e-9
            and wb.depletion_fraction(0.9, 0.0) == 0.8)          # clamped


def case_depletion_from_volumetric_sensor():
    # 31 % on the Vertisol: (0.40 - 0.31) * 750 = 67.5 mm below field capacity.
    dr, problem = wb.depletion_from_sensor(31.0, 0.40, 0.22, 0.75)
    fraction, _ = wb.depletion_from_sensor(0.31, 0.40, 0.22, 0.75)
    faulty, why = wb.depletion_from_sensor(95.0, 0.40, 0.22, 0.75)
    return (abs(dr - 67.5) < 1e-9 and problem is None and abs(fraction - 67.5) < 1e-9
            and faulty is None and "sensor" in why)


def case_stress_coefficient_follows_eq_84():
    # TAW 100, p 0.5: Ks = 1 up to RAW (50); at Dr 75 -> (100-75)/(0.5*100) = 0.5.
    return (wb.stress_coefficient(40, 100, 0.5) == 1.0
            and abs(wb.stress_coefficient(75, 100, 0.5) - 0.5) < 1e-9)


def case_rain_is_probability_weighted():
    # 20 mm at 30 % -> 6 mm expected -> 80 % effective = 4.8 mm.
    return (abs(wb.effective_rain(20, 30) - 4.8) < 1e-9
            and abs(wb.effective_rain(20, None) - 16.0) < 1e-9
            and abs(wb.effective_rain(100, 100) - (40 + 20)) < 1e-9)   # runoff above 50 mm


def case_salinity_follows_maas_hoffman_and_fao29():
    return (abs(wb.relative_yield_percent(10.0, 7.7, 5.2) - 88.04) < 0.01
            and abs(wb.leaching_requirement(1.5, 2.5) - 1.5 / 11.0) < 1e-9
            and wb.leaching_requirement(15.0, 2.5) is None)


def case_hargreaves_is_close_to_penman_monteith():
    # Ahmedabad 23 Sep: Open-Meteo Penman-Monteith 5.19 mm; Hargreaves within 15 %.
    et0 = wb.et0_hargreaves(26.1, 35.0, 23.02, date(2026, 9, 23))
    return abs(et0 - 5.19) / 5.19 < 0.15


def case_stage_from_days_after_sowing():
    # Groundnut, 130-day season (FAO-56 stage shares 15/25/40/20 %).
    season = 130
    return ([wb.stage_from_days(d, season) for d in (3, 15, 40, 60, 90, 110, 128)]
            == ["germination", "seedling", "vegetative", "flowering", "fruiting",
                "maturation", "harvest_ready"])


# ---------------------------------------------------------------------------
# The bugs that were fixed - each must stay fixed
# ---------------------------------------------------------------------------
def case_emergency_fires_before_the_wilting_point():
    """The old trigger sat below the wilting point on 10 of 15 crop/soil pairs."""
    for crop in ("cotton", "wheat", "maize", "potato"):
        for soil in ("clay", "loamy", "silt", "black_cotton"):
            c, s = CROP_CONFIG[crop], SOIL_CONFIG[soil]
            fc = 1000 * s["theta_fc"] * c["root_depth_m"]
            wp = 1000 * s["theta_wp"] * c["root_depth_m"]
            emergency_water = fc - EMERGENCY_DEPLETION * (fc - wp)
            if not emergency_water > wp:
                return False
    return True


async def case_near_wilting_is_an_emergency():
    # Clay 0.36/0.22, cotton 1.2 m: WP at 22.5 % -> 0.225 is 97 % depleted.
    p = await plan(crop="cotton", growth_stage="vegetative", soil_type="clay",
                   soil_moisture_percent=22.5)
    return first(p)["decision_code"] == "EMERGENCY_IRRIGATE" \
        and first(p)["irrigation_required"]


async def case_no_drainage_from_drying_soil():
    """Without rain or irrigation, depletion rises by exactly ETc - nothing drains."""
    p = await plan(crop="cotton", growth_stage="vegetative", soil_type="sandy",
                   soil_moisture_percent=11.0, weather_data=forecast(days=2, et0=4.0))
    d0, d1 = p["irrigation_schedule"][:2]
    etc = d1["water_balance_mm"]["etc_mm"]
    rise = d1["water_balance_mm"]["depletion_mm"] - d0["water_balance_mm"]["depletion_mm"]
    return d0["decision_code"].startswith("SKIP") and abs(rise - etc) < 0.2


async def case_every_crop_the_crop_agent_recommends_is_known():
    for crop in ("Groundnut", "Guar", "White Peas", "Coriander (Leaves)", "Ajwain",
                 "Mango", "Cotton", "Potato", "Tomato"):
        p = await plan(crop=crop, growth_stage="vegetative", soil_type="Black Cotton",
                       soil_moisture_percent=30)
        if p["crop_profile"]["crop"] == "unspecified":
            return False
    return True


async def case_unknown_crop_is_rejected_not_planned_as_wheat():
    try:
        await plan(crop="dragonfruitt", soil_type="loamy")
        return False
    except ValueError as exc:
        return "Supported" in str(exc)


async def case_rain_at_low_probability_does_not_skip_irrigation():
    """20 mm forecast at 20 % must not stop a needed irrigation."""
    p = await plan(crop="cotton", growth_stage="flowering", soil_type="loamy",
                   soil_moisture_percent=15.0,
                   weather_data=forecast(rain={0: 20.0, 1: 20.0}, pop={0: 20.0, 1: 20.0}))
    return first(p)["decision_code"] == "IRRIGATE"


async def case_waits_for_likely_rain_when_safe():
    """Just past the trigger, far from wilting, and 40 mm is 90 % likely tomorrow.

    Loam, cotton 1.2 m, 16 %: ~112 mm depleted vs RAW ~109 mm. Tomorrow's rain
    (28.8 mm effective) brings it back to ~83 mm, inside RAW: irrigating today
    would waste water. The same soil with no rain coming must irrigate.
    """
    wait = await plan(crop="cotton", growth_stage="vegetative", soil_type="loamy",
                      soil_moisture_percent=16.0,
                      weather_data=forecast(rain={1: 40.0}, pop={1: 90.0}))
    dry = await plan(crop="cotton", growth_stage="vegetative", soil_type="loamy",
                     soil_moisture_percent=16.0)
    return first(wait)["decision_code"] == "SKIP_RAIN" and first(dry)["decision_code"] == "IRRIGATE"


async def case_heavy_rain_postpones_irrigation():
    p = await plan(crop="cotton", growth_stage="vegetative", soil_type="loamy",
                   soil_moisture_percent=18.0,
                   weather_data=forecast(rain={0: 90.0}, pop={0: 80.0}))
    return first(p)["decision_code"] == "POSTPONE_STORM" and not first(p)["irrigation_required"]


async def case_within_readily_available_water_no_irrigation():
    # Loam 0.25/0.12, cotton 1.2 m: 22 % is 36 mm depleted, below RAW (~94 mm).
    p = await plan(crop="cotton", growth_stage="vegetative", soil_type="loamy",
                   soil_moisture_percent=22.0)
    return first(p)["decision_code"] in ("SKIP_DEFICIT_SMALL", "SKIP_SATURATED")


async def case_gross_depth_covers_application_losses():
    drip = await plan(crop="cotton", growth_stage="flowering", soil_type="loamy",
                      soil_moisture_percent=15.0, irrigation_method="drip")
    flood = await plan(crop="cotton", growth_stage="flowering", soil_type="loamy",
                       soil_moisture_percent=15.0, irrigation_method="flood")
    d, f = first(drip), first(flood)
    return (abs(d["water_depth_mm"] - d["net_irrigation_mm"] / 0.90) < 0.2
            and abs(f["water_depth_mm"] - f["net_irrigation_mm"] / 0.50) < 0.2
            and f["water_depth_mm"] > d["water_depth_mm"])


async def case_critical_stage_irrigates_earlier():
    """At a yield-critical stage the allowed depletion is 20 % tighter.

    Checked on the profile's RAW, which excludes the ETc adjustment, so the
    rule is tested on its own and not through the stages' different Kc.
    """
    veg = await plan(crop="groundnut", growth_stage="vegetative", soil_type="loamy",
                     soil_moisture_percent=20.0)
    flower = await plan(crop="groundnut", growth_stage="flowering", soil_type="loamy",
                        soil_moisture_percent=20.0)
    ratio = (flower["crop_profile"]["readily_available_water_mm"]
             / veg["crop_profile"]["readily_available_water_mm"])
    return abs(ratio - 0.8) < 0.01


async def case_long_application_is_split_over_days():
    # 100+ mm gross by drip at 3 mm/h needs >30 h: several 8-hour sets.
    p = await plan(crop="cotton", growth_stage="flowering", soil_type="black_cotton",
                   soil_moisture_percent=25.0, irrigation_method="drip")
    d = first(p)
    return d["sets"] and d["sets"] > 1 and d["duration_hours"] <= 8.0 \
        and "split over" in d["recommendation"]


async def case_windy_day_switches_sprinkler_off():
    p = await plan(crop="wheat", growth_stage="flowering", soil_type="loamy",
                   soil_moisture_percent=13.0, irrigation_method="sprinkler",
                   weather_data=forecast(wind=25.0))
    d = first(p)
    return d["method"] != "sprinkler" and any(r["code"] == "WIND_SPRAY_LIMIT" for r in d["reasons"])


async def case_salinity_above_crop_threshold_alerts_with_yield():
    tolerant = await plan(crop="cotton", growth_stage="vegetative", soil_type="loamy",
                          soil_moisture_percent=20.0, electrical_conductivity=4.0)
    sensitive = await plan(crop="potato", growth_stage="vegetative", soil_type="loamy",
                           soil_moisture_percent=20.0, electrical_conductivity=4.0)
    return (not any(a["type"] == "salinity" for a in tolerant["alerts"])
            and any(a["type"] == "salinity" and "72%" in a["message"]
                    for a in sensitive["alerts"]))       # 100 - 12*(4-1.7) = 72.4


async def case_leaching_fraction_added_when_water_ec_known():
    base = await plan(crop="tomato", growth_stage="fruiting", soil_type="loamy",
                      soil_moisture_percent=15.0, irrigation_method="drip")
    leach = await plan(crop="tomato", growth_stage="fruiting", soil_type="loamy",
                       soil_moisture_percent=15.0, irrigation_method="drip", water_ec_ds_m=1.5)
    lr = 1.5 / 11.0
    return abs(first(leach)["water_depth_mm"] - first(base)["water_depth_mm"] / (1 - lr)) < 0.3


async def case_rice_keeps_standing_water():
    p = await plan(crop="rice", growth_stage="vegetative", soil_type="clay")
    drain = await plan(crop="rice", growth_stage="harvest_ready", soil_type="clay")
    codes = {d["decision_code"] for d in p["irrigation_schedule"]}
    return codes <= {"MAINTAIN_FLOOD", "SKIP_SATURATED", "SKIP_RAIN"} \
        and first(drain)["decision_code"] == "DRAIN_FIELD"


async def case_no_moisture_reading_is_disclosed():
    p = await plan(crop="cotton", growth_stage="vegetative", soil_type="loamy")
    return (p["status"] == "partial"
            and any("No usable soil moisture" in w for w in p["warnings"])
            and any(a["action_code"] == "INSPECT_SOIL" for a in p["farmer_actions"]))


async def case_soil_readings_are_never_invented():
    p = await plan(crop="cotton", growth_stage="vegetative", soil_type="loamy",
                   soil_moisture_percent=20.0)
    s = p["soil_health_insights"]
    return s["npk_status"] == {"nitrogen": None, "phosphorus": None, "potassium": None} \
        and s["soil_ph"] is None


async def case_hargreaves_used_when_no_penman_value():
    p = await plan(crop="cotton", growth_stage="vegetative", soil_type="loamy",
                   soil_moisture_percent=20.0, weather_data=forecast(et0=None))
    return p["crop_profile"]["et0_source"] == "hargreaves_fallback" \
        and any("Hargreaves" in w for w in p["warnings"])


async def case_days_after_sowing_sets_the_stage():
    p = await plan(crop="groundnut", days_after_sowing=60, soil_type="loamy",
                   soil_moisture_percent=20.0)
    return p["crop_profile"]["growth_stage"] == "flowering"


# ---------------------------------------------------------------------------
# Contract: schema, orchestrator, scheduler, API
# ---------------------------------------------------------------------------
async def case_output_validates_and_keeps_scheduler_fields():
    from AI_Backend.agents.farm_operations_automation.task_scheduler.schemas import (
        IrrigationAgentData)
    from AI_Backend.agents.farm_operations_automation.task_scheduler.adapters import irrigation_output_to_scheduler_block

    p = await plan(crop="cotton", growth_stage="flowering", soil_type="loamy",
                   soil_moisture_percent=15.0, farm_area_hectares=2.0)
    IrrigationPlannerResponse.model_validate(p)
    block = IrrigationAgentData.model_validate(
        irrigation_output_to_scheduler_block(p, reference_date=date(2026, 9, 22)))
    return (block.schedule and block.schedule[0].irrigation_required
            and block.schedule[0].water_volume_liters == first(p)["water_depth_mm"] * 20_000
            and block.soil_moisture_current_percent is not None)


async def case_orchestrator_node_writes_irrigation_advice():
    from langgraph.graph import END, START, StateGraph

    from typing import Optional, TypedDict

    # Functional form on purpose: this module uses postponed annotations, so a
    # class-based TypedDict would hand LangGraph strings to resolve in module
    # scope, where `Optional` is not defined.
    FarmState = TypedDict("FarmState", {
        "query": str, "lat": float, "lon": float,
        "weather_data": Optional[dict], "soil_data": Optional[dict],
        "irrigation_advice": Optional[dict], "crop_recommendation": Optional[dict],
    })

    graph = StateGraph(FarmState)
    graph.add_node("irrigation", AGENT)
    graph.add_edge(START, "irrigation")
    graph.add_edge("irrigation", END)
    ok = await graph.compile().ainvoke({
        "query": "", "lat": 23.02, "lon": 72.57, "soil_data": {"soil_moisture": 20.0},
        "weather_data": forecast(), "irrigation_advice": None, "crop_recommendation": None})
    bad = await graph.compile().ainvoke({
        "query": "", "lat": 23.02, "lon": 72.57, "soil_data": {"soil_type": "moonrock"},
        "weather_data": forecast(), "irrigation_advice": None, "crop_recommendation": None})
    return (ok["irrigation_advice"]["irrigation_schedule"]
            and bad["irrigation_advice"]["status"] == "invalid_input")


def case_router_plans_without_a_database():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from AI_Backend.routers import irrigation_planner as router_module

    app = FastAPI()
    app.include_router(router_module.router)
    client = TestClient(app)
    original = router_module.irrigation_agent.service._get_weather

    async def fake_weather(_data):
        return forecast()

    router_module.irrigation_agent.service._get_weather = fake_weather
    try:
        ok = client.post("/irrigation-planner/plan", json={
            "location": LOCATION, "crop": "groundnut", "days_after_sowing": 60,
            "soil_type": "Black Cotton", "soil_moisture_percent": 27, "farm_id": "farm-1"})
        bad = client.post("/irrigation-planner/plan", json={
            "location": LOCATION, "crop": "banana-split"})
        options = client.get("/irrigation-planner/options").json()
    finally:
        router_module.irrigation_agent.service._get_weather = original
    return (ok.status_code == 200 and ok.json()["crop_profile"]["crop"] == "groundnut"
            and bad.status_code == 422 and "groundnut" in options["crops"])


CASES = [
    case_extraterrestrial_radiation_matches_fao_example_8,
    case_taw_and_p_adjustment,
    case_depletion_from_volumetric_sensor,
    case_stress_coefficient_follows_eq_84,
    case_rain_is_probability_weighted,
    case_salinity_follows_maas_hoffman_and_fao29,
    case_hargreaves_is_close_to_penman_monteith,
    case_stage_from_days_after_sowing,
    case_emergency_fires_before_the_wilting_point,
    case_near_wilting_is_an_emergency,
    case_no_drainage_from_drying_soil,
    case_every_crop_the_crop_agent_recommends_is_known,
    case_unknown_crop_is_rejected_not_planned_as_wheat,
    case_rain_at_low_probability_does_not_skip_irrigation,
    case_waits_for_likely_rain_when_safe,
    case_heavy_rain_postpones_irrigation,
    case_within_readily_available_water_no_irrigation,
    case_gross_depth_covers_application_losses,
    case_critical_stage_irrigates_earlier,
    case_long_application_is_split_over_days,
    case_windy_day_switches_sprinkler_off,
    case_salinity_above_crop_threshold_alerts_with_yield,
    case_leaching_fraction_added_when_water_ec_known,
    case_rice_keeps_standing_water,
    case_no_moisture_reading_is_disclosed,
    case_soil_readings_are_never_invented,
    case_hargreaves_used_when_no_penman_value,
    case_days_after_sowing_sets_the_stage,
    case_output_validates_and_keeps_scheduler_fields,
    case_orchestrator_node_writes_irrigation_advice,
    case_router_plans_without_a_database,
]


def main() -> bool:
    logging.disable(logging.CRITICAL)
    passed = 0
    for case in CASES:
        name = case.__name__.removeprefix("case_").replace("_", " ")
        try:
            ok = bool(asyncio.run(case()) if asyncio.iscoroutinefunction(case) else case())
        except Exception as exc:  # noqa: BLE001
            ok = False
            name = f"{name}  ({type(exc).__name__}: {str(exc)[:160]})"
        passed += ok
        print(f"[{'PASS' if ok else 'FAIL'}] {name}")
    print(f"\n{passed}/{len(CASES)} checks passed")
    return passed == len(CASES)


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
