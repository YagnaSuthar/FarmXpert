"""Regression suite for the Soil Health agent.

    python -m AI_Backend.tests.test_soil_health
"""
from __future__ import annotations

import asyncio
import logging
import sys
from datetime import date

from AI_Backend.agents.crop_planning_growth.soil_health.agent import SoilHealthAgent
from AI_Backend.agents.crop_planning_growth.soil_health.config import CROP_CONFIG
from AI_Backend.agents.crop_planning_growth.soil_health.schemas import SoilHealthOutput

AGENT = SoilHealthAgent()
GOOD = dict(soil_temperature=26.0, soil_ph=7.0, nitrogen=60.0, phosphorus=18.0,
            potassium=120.0, electrical_conductivity=0.6, air_temperature=30.0,
            air_humidity=60.0)


def run(**kw):
    return asyncio.run(AGENT.run({**GOOD, **kw}))


def types(result, contains=""):
    return {a["type"]: a["severity"] for a in result["alerts"] if contains in a["type"]}


# ---------------------------------------------------------------------------
# Moisture as plant-available water (the v2 bug: field capacity read as drought)
# ---------------------------------------------------------------------------
def case_field_capacity_is_never_dry():
    """FAO-56 field capacity for each soil must raise no moisture alert."""
    for soil, fc in (("sandy", 12), ("loamy", 25), ("clay", 36), ("Black Cotton", 40),
                     ("Red Laterite", 22)):
        r = run(soil_moisture=fc, soil_type=soil, crop_type="wheat")
        if types(r, "MOIST") or r["moisture_status"]["available_water_percent"] != 100.0:
            return False
    return True


def case_same_reading_different_soil_different_verdict():
    loam = run(soil_moisture=25, soil_type="loamy", crop_type="wheat")
    clay = run(soil_moisture=25, soil_type="clay", crop_type="wheat")
    return not types(loam, "MOIST") and types(clay, "MOIST") == {"LOW_MOISTURE": "high"}


def case_wilting_and_waterlogging_extremes():
    wilt = run(soil_moisture=13, soil_type="loamy")      # AW 7.7 %
    wet = run(soil_moisture=31, soil_type="loamy")       # 6 points above FC
    soaked = run(soil_moisture=38, soil_type="loamy")    # 13 above FC
    return (types(wilt, "MOIST") == {"CRITICAL_LOW_MOISTURE": "critical"}
            and types(wet, "MOIST") == {"HIGH_MOISTURE": "medium"}
            and types(soaked, "MOIST") == {"CRITICAL_HIGH_MOISTURE": "critical"})


def case_crop_depletion_fraction_sets_the_stress_point():
    """Loam at AW 50 %: potato (p 0.35, stress below 65 %) is short of water;
    cotton (p 0.65, stress below 35 %) is fine."""
    reading = 18.5     # (0.185-0.12)/(0.25-0.12) = 50 %
    potato = run(soil_moisture=reading, soil_type="loamy", crop_type="potato")
    cotton = run(soil_moisture=reading, soil_type="loamy", crop_type="cotton")
    return ("LOW_MOISTURE" in types(potato, "MOIST") and not types(cotton, "MOIST")
            and potato["moisture_status"]["stress_starts_below_percent"] == 65.0)


def case_paddy_wants_standing_water():
    flooded = run(soil_moisture=45, soil_type="clay", crop_type="rice")
    drying = run(soil_moisture=30, soil_type="clay", crop_type="rice")
    return not types(flooded, "MOIST") and "LOW_MOISTURE" in types(drying, "MOIST")


# ---------------------------------------------------------------------------
# Salinity against the crop's Maas-Hoffman tolerance
# ---------------------------------------------------------------------------
def case_salinity_uses_crop_tolerance_and_reports_yield():
    potato = run(electrical_conductivity=3.0, crop_type="potato", soil_moisture=25, soil_type="loamy")
    cotton = run(electrical_conductivity=3.0, crop_type="cotton", soil_moisture=25, soil_type="loamy")
    guar = run(electrical_conductivity=5.0, crop_type="guar", soil_moisture=25, soil_type="loamy")
    alert = next(a for a in potato["alerts"] if a["type"] == "HIGH_EC")
    # 100 - 12 * (3.0 - 1.7) = 84.4 %
    return (abs(alert["expected_relative_yield"] - 84.4) < 0.05 and alert["severity"] == "medium"
            and not types(cotton, "EC") and not types(guar, "EC"))


def case_extreme_value_escalates_only_its_own_alert():
    """pH 4.0 is extreme; the EC alert beside it must keep its own severity.
    v2 turned every alert critical when any one parameter was extreme."""
    r = run(soil_ph=4.0, electrical_conductivity=2.6)      # no crop: general thresholds
    ec = next(a for a in r["alerts"] if a["type"] == "HIGH_EC")
    return (types(r, "PH") == {"CRITICAL_LOW_PH": "critical"}
            and ec["severity"] != "critical" and not ec.get("extreme_override"))


# ---------------------------------------------------------------------------
# Agronomic advice
# ---------------------------------------------------------------------------
def fertilizers(result):
    return {f["triggered_by"]: f for f in result["fertilizers"]}


def case_legumes_get_rhizobium_not_urea():
    legume = fertilizers(run(nitrogen=15, crop_type="groundnut", soil_type="loamy", soil_moisture=25,
                             nutrient_source="lab"))
    cereal = fertilizers(run(nitrogen=15, crop_type="maize", soil_type="loamy", soil_moisture=25,
                             nutrient_source="lab"))
    return (legume["LOW_N"]["fertilizer"] == "rhizobium_plus_starter_n"
            and cereal["LOW_N"]["fertilizer"] == "urea")


def case_gypsum_only_for_sodic_salinity():
    saline = fertilizers(run(electrical_conductivity=6.0, soil_ph=7.6))
    sodic = fertilizers(run(electrical_conductivity=6.0, soil_ph=8.7))
    return (saline["CRITICAL_HIGH_EC"]["fertilizer"] == "none"
            and "leaching" in saline["CRITICAL_HIGH_EC"]["display_name"].lower()
            and sodic["CRITICAL_HIGH_EC"]["fertilizer"] == "gypsum")


def case_no_hazardous_or_uneconomic_alkalinity_advice():
    r = run(soil_ph=9.2, soil_type="black_cotton", soil_moisture=35)
    text = " ".join(s["message"] for s in r["suggestions"]).lower() + " ".join(
        f["display_name"] + f["dosage"] for f in r["fertilizers"]).lower()
    return ("sulphuric" not in text and "sulfuric" not in text
            and fertilizers(r)["CRITICAL_HIGH_PH"]["fertilizer"] == "gypsum")


def case_sensor_npk_is_advisory_and_never_dosed():
    """7-in-1 probes estimate NPK from conductivity: flag, never fertilize on it."""
    sensor = run(nitrogen=5, phosphorus=2, potassium=20, crop_type="maize", soil_type="loamy",
                 soil_moisture=25)
    nutrient_alerts = [a for a in sensor["alerts"]
                       if a["parameter"] in ("nitrogen", "phosphorus", "potassium")]
    recs = sensor["fertilizers"]
    return (nutrient_alerts and all(a["severity"] in ("info", "low") and a["estimated"]
                                    and "confirm with a soil test" in a["message"]
                                    for a in nutrient_alerts)
            and [r["fertilizer"] for r in recs] == ["soil_test_first"]
            and not {"CRITICAL_LOW_N", "CRITICAL_LOW_P", "CRITICAL_LOW_K"} & set(sensor["critical_factors"]))


def case_lab_npk_gets_full_recommendations():
    lab = run(nitrogen=5, phosphorus=2, potassium=20, crop_type="maize", soil_type="loamy",
              soil_moisture=25, nutrient_source="lab")
    doses = {r["fertilizer"] for r in lab["fertilizers"]}
    return {"ammonium_sulfate", "sspa", "mop"} <= doses and "CRITICAL_LOW_N" in lab["critical_factors"]


def case_crop_practice_is_suggested():
    r = run(crop_type="groundnut", soil_type="loamy", soil_moisture=25)
    return any(s["source"] == "crop" and "Gypsum 500 kg/ha at pegging" in s["message"]
               for s in r["suggestions"])


# ---------------------------------------------------------------------------
# Robustness and the v2 bugs
# ---------------------------------------------------------------------------
def case_unknown_names_never_crash():
    r = run(crop_type="dragonfruit", soil_type="moonrock", soil_moisture=25)
    fields = {e["field"] for e in r["validation_errors"]}
    return fields == {"crop_type", "soil_type"} and r["soil_health_score"] >= 0


def case_names_from_other_agents_and_the_database():
    for crop, soil in (("paddy", "Loam"), ("peanut", "Black Cotton"), ("Coriander (Leaves)", "Red Laterite"),
                       ("White Peas", "Sandy Loam"), ("Groundnut", "Clay Loam")):
        r = run(crop_type=crop, soil_type=soil, soil_moisture=25)
        if r["validation_errors"]:
            return False
    return True


def case_ph_and_ec_alone_are_enough():
    r = asyncio.run(AGENT.run({"soil_ph": 7.2, "electrical_conductivity": 0.5}))
    return r["soil_health_score"] > 0 and r["data_quality_score"] < 0.6 and r["moisture_status"] is None


def case_complete_input_scores_full_data_quality():
    r = run(soil_moisture=25, soil_type="loamy", crop_type="wheat", rainfall=10,
            fertilizer_type="urea")
    return r["data_quality_score"] == 1.0


def case_score_does_not_depend_on_the_season_label():
    scores = {run(soil_moisture=25, soil_type="loamy", crop_type="wheat", season=s)["soil_health_score"]
              for s in ("summer", "winter", "monsoon", None)}
    return len(scores) == 1


def case_orchestrator_node_never_raises():
    async def go():
        return await AGENT({"lat": 23.0, "lon": 72.5, "soil_data": {"soil_moisture": 20}})
    return asyncio.run(go()) == {}


def case_every_crop_has_irrigation_water_data():
    """Moisture stress uses the irrigation planner's FAO-56 p for the crop."""
    from AI_Backend.agents.crop_planning_growth.irrigation_planner.config import CROP_CONFIG as IRR
    return set(CROP_CONFIG) <= set(IRR)


def case_every_crop_the_crop_agent_recommends_is_known():
    from AI_Backend.agents.crop_planning_growth.soil_health.service import canonical_crop
    return all(canonical_crop(c) for c in ("Ajwain", "Coriander (Leaves)", "Cotton", "Groundnut",
                                           "Guar", "Mango", "Potato", "Tomato", "White Peas"))


# ---------------------------------------------------------------------------
# Contract: schema, scheduler, irrigation, API
# ---------------------------------------------------------------------------
def case_output_validates_against_schema():
    r = run(soil_moisture=14, soil_type="loamy", crop_type="potato", electrical_conductivity=3.0,
            nitrogen=15, fertilizer_type="urea")
    SoilHealthOutput.model_validate(r)
    return True


def case_scheduler_adapter_accepts_the_output():
    from AI_Backend.agents.farm_operations_automation.task_scheduler.schemas import SoilHealthAgentData
    from AI_Backend.agents.farm_operations_automation.task_scheduler.adapters import soil_health_output_to_scheduler_block

    r = run(soil_moisture=14, soil_type="loamy", crop_type="maize", nitrogen=15)
    block = SoilHealthAgentData.model_validate(soil_health_output_to_scheduler_block(r))
    return block.soil_health_score == r["soil_health_score"] and block.alerts


def case_irrigation_now_uses_soil_health():
    from AI_Backend.agents.crop_planning_growth.irrigation_planner.agent import IrrigationAgent

    days = [{"date": date(2026, 9, 22 + i).isoformat(), "temp_min": 25, "temp_max": 34,
             "rainfall_mm": 0, "rain_probability_percent": 5, "humidity": 60, "wind_speed": 8,
             "et0_mm": 5.0} for i in range(3)]
    plan = asyncio.run(IrrigationAgent().run({
        "weather_data": {"location": {"lat": 23.0, "lon": 72.5}, "forecast_short_term": days},
        "crop": "potato", "growth_stage": "vegetative", "soil_type": "loamy",
        "soil_data": {"soil_moisture": 20, "soil_ph": 7.1, "electrical_conductivity": 3.5}}))
    insights = plan["soil_health_insights"]
    return insights["health_score"] is not None and insights["health_status"]


def case_router_contract():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from AI_Backend.routers.soil_health import router

    app = FastAPI()
    app.include_router(router, prefix="/api/soil-health")
    client = TestClient(app)
    ok = client.post("/api/soil-health/analyze", json={
        "soil_ph": 8.1, "electrical_conductivity": 0.6, "soil_moisture": 28,
        "soil_type": "Black Cotton", "crop_type": "groundnut"})
    missing = client.post("/api/soil-health/analyze", json={"soil_moisture": 28})
    options = client.get("/api/soil-health/options").json()
    return (ok.status_code == 200 and ok.json()["moisture_status"]["soil_type_used"] == "black_cotton"
            and missing.status_code == 422 and "groundnut" in options["crops"])


CASES = [
    case_field_capacity_is_never_dry,
    case_same_reading_different_soil_different_verdict,
    case_wilting_and_waterlogging_extremes,
    case_crop_depletion_fraction_sets_the_stress_point,
    case_paddy_wants_standing_water,
    case_salinity_uses_crop_tolerance_and_reports_yield,
    case_extreme_value_escalates_only_its_own_alert,
    case_legumes_get_rhizobium_not_urea,
    case_gypsum_only_for_sodic_salinity,
    case_no_hazardous_or_uneconomic_alkalinity_advice,
    case_sensor_npk_is_advisory_and_never_dosed,
    case_lab_npk_gets_full_recommendations,
    case_crop_practice_is_suggested,
    case_unknown_names_never_crash,
    case_names_from_other_agents_and_the_database,
    case_ph_and_ec_alone_are_enough,
    case_complete_input_scores_full_data_quality,
    case_score_does_not_depend_on_the_season_label,
    case_orchestrator_node_never_raises,
    case_every_crop_has_irrigation_water_data,
    case_every_crop_the_crop_agent_recommends_is_known,
    case_output_validates_against_schema,
    case_scheduler_adapter_accepts_the_output,
    case_irrigation_now_uses_soil_health,
    case_router_contract,
]


def main() -> bool:
    logging.disable(logging.CRITICAL)
    passed = 0
    for case in CASES:
        name = case.__name__.removeprefix("case_").replace("_", " ")
        try:
            ok = bool(case())
        except Exception as exc:  # noqa: BLE001
            ok = False
            name = f"{name}  ({type(exc).__name__}: {str(exc)[:160]})"
        passed += ok
        print(f"[{'PASS' if ok else 'FAIL'}] {name}")
    print(f"\n{passed}/{len(CASES)} checks passed")
    return passed == len(CASES)


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
