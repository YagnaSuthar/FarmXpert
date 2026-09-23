"""Every agent, every farm condition - invariants that must always hold.

Sweeps the four agents across extreme and awkward farms - Thar heat, Ladakh
frost, cyclone rain, monsoon deluge, southern hemisphere, arctic summer,
gappy and empty provider data, every crop x soil x moisture extreme, odd but
legal inputs - and checks on every output:

  * no exception, strict JSON (no NaN / Infinity), the agent's own schema
  * physical bounds (depths >= 0, gross >= net, depletion within the root
    zone, scores 0-100, one working day per irrigation set)
  * crop and soil names from any agent are understood by every other agent

plus the agronomic rules for the edge conditions themselves (frozen ground,
crop maturity, a sowing date past the season, perennials, cold spraying).
Runs offline: all provider data is fabricated.

    python -m AI_Backend.tests.test_farm_conditions
"""
import asyncio
import itertools
import json
import logging
import math
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone

import httpx

logging.disable(logging.CRITICAL)

FAIL = defaultdict(list)
RUNS = Counter()


def record(agent, label, problem):
    FAIL[agent].append(f"{label}: {problem}")


def strict_json(obj):
    json.dumps(obj, allow_nan=False, default=str)


# ─────────────────────────────────────────────────────────────────────────────
# WEATHER - fabricated provider payloads for extreme climates
# ─────────────────────────────────────────────────────────────────────────────
from AI_Backend.agents.crop_planning_growth.weather_watcher import service as wsvc
from AI_Backend.agents.crop_planning_growth.weather_watcher.agent import WeatherAgent
from AI_Backend.agents.crop_planning_growth.weather_watcher.schemas import WeatherWatcherOutput

wsvc.HTTP_BACKOFF_SECONDS = 0.0

CLIMATES = {
    # name: (lat, lon, utc_offset_s, tmin, tmax, rh, rain_mm_day, wind)
    "thar_heat":      (27.0, 71.0, 19800, 32, 49, 8, 0, 20),
    "ladakh_frost":   (34.1, 77.6, 19800, -18, -2, 40, 0, 15),
    "monsoon_deluge": (19.1, 72.9, 19800, 24, 28, 98, 260, 55),
    "cyclone":        (20.0, 86.0, 19800, 24, 29, 95, 400, 140),
    "sydney_winter":  (-33.9, 151.2, 36000, 8, 17, 70, 3, 18),
    "california":     (36.7, -119.8, -25200, 12, 35, 30, 0, 10),
    "arctic_summer":  (68.0, 23.0, 7200, 5, 14, 75, 1, 12),
    "equator_wet":    (0.3, 32.6, 10800, 17, 27, 85, 12, 8),
    "calm_humid":     (23.0, 72.5, 19800, 26, 34, 88, 2, 0),
}


def om_payload(lat, offset, tmin, tmax, rh, rain, wind, gaps=False, empty=False):
    tz = timezone(timedelta(seconds=offset))
    today = datetime.now(tz).date()
    n = 0 if empty else 14
    times = [(today + timedelta(days=i)).isoformat() for i in range(n)]
    daily = {"time": times,
             "temperature_2m_max": [tmax] * n, "temperature_2m_min": [tmin] * n,
             "precipitation_sum": [rain] * n, "precipitation_probability_max": [90 if rain else 5] * n,
             "wind_speed_10m_max": [wind] * n, "relative_humidity_2m_mean": [rh] * n,
             "et0_fao_evapotranspiration": [max(0.1, 0.2 * (tmax - tmin))] * n}
    start = datetime.combine(today, datetime.min.time())
    hours = [start + timedelta(hours=h) for h in range(n * 24)]
    hourly = {"time": [h.isoformat(timespec="minutes") for h in hours],
              "temperature_2m": [tmin + (tmax - tmin) * (0.5 + 0.5 * math.sin((h.hour - 9) / 24 * 2 * math.pi)) for h in hours],
              "relative_humidity_2m": [rh] * len(hours),
              "precipitation": [rain / 24] * len(hours),
              "precipitation_probability": [90 if rain else 5] * len(hours),
              "wind_speed_10m": [wind] * len(hours),
              "is_day": [1 if 6 <= h.hour < 19 else 0 for h in hours]}
    if gaps:
        for key in ("temperature_2m_max", "precipitation_sum", "relative_humidity_2m_mean"):
            daily[key][3] = None
        for key in ("temperature_2m", "relative_humidity_2m"):
            for i in range(10, 40):
                hourly[key][i] = None
    return {"timezone": "X", "utc_offset_seconds": offset, "daily": daily, "hourly": hourly,
            "current": {"temperature_2m": tmax - 2, "relative_humidity_2m": rh,
                        "precipitation": rain / 24, "wind_speed_10m": wind, "weather_code": 63 if rain else 0}}


def weather_agent_for(payload):
    def handler(request):
        if "open-meteo" in request.url.host:
            return httpx.Response(200, json=payload)
        return httpx.Response(503)
    return WeatherAgent(api_key="", transport=httpx.MockTransport(handler))


def check_weather(label, out):
    strict_json(out)
    WeatherWatcherOutput.model_validate(out)
    days = out["forecast_short_term"] + out["forecast_long_term"]
    dates = [d["date"] for d in days]
    if dates != sorted(dates) or len(set(dates)) != len(dates):
        record("weather", label, "days unsorted or duplicated")
    for d in days:
        if d["temp_min"] > d["temp_max"]:
            record("weather", label, f"tmin>tmax on {d['date']}")
        if d.get("et0_mm") is not None and d["et0_mm"] < 0:
            record("weather", label, "negative ET0")
    adv = out.get("agro_advisory") or {}
    for w in adv.get("spray_windows", []):
        if w["hours"] < 2:
            record("weather", label, "spray window < 2 h")


async def sweep_weather():
    results = {}
    for name, (lat, lon, off, tmin, tmax, rh, rain, wind) in CLIMATES.items():
        for variant in ("normal", "gaps", "empty"):
            wsvc.clear_cache()
            payload = om_payload(lat, off, tmin, tmax, rh, rain, wind,
                                 gaps=variant == "gaps", empty=variant == "empty")
            label = f"{name}/{variant}"
            RUNS["weather"] += 1
            try:
                out = await weather_agent_for(payload).run({"lat": lat, "lon": lon})
                check_weather(label, out)
                results[label] = out
            except Exception as exc:  # noqa: BLE001
                record("weather", label, f"{type(exc).__name__}: {exc}")
    return results


# ─────────────────────────────────────────────────────────────────────────────
# IRRIGATION
# ─────────────────────────────────────────────────────────────────────────────
from AI_Backend.agents.crop_planning_growth.irrigation_planner.agent import IrrigationAgent
from AI_Backend.agents.crop_planning_growth.irrigation_planner.config import (
    CROP_CONFIG as IRR_CROPS, METHODS, SOIL_CONFIG as IRR_SOILS)

IRR = IrrigationAgent()


def check_irrigation(label, plan):
    strict_json(plan)
    cp = plan["crop_profile"]
    taw = cp["total_available_water_mm"]
    for d in plan["irrigation_schedule"]:
        wb = d["water_balance_mm"]
        for k, v in wb.items():
            if v is None or (isinstance(v, float) and not math.isfinite(v)):
                record("irrigation", label, f"{k} not finite")
        if d["water_depth_mm"] is not None and d["water_depth_mm"] < 0:
            record("irrigation", label, "negative depth")
        if d["net_irrigation_mm"] and d["water_depth_mm"] + 1e-6 < d["net_irrigation_mm"]:
            record("irrigation", label, "gross < net")
        if cp["water_management"] == "upland":
            dep = wb.get("depletion_mm")
            if dep is None or dep < -1e-6 or dep > taw + 1e-6:
                record("irrigation", label, f"depletion {dep} outside [0,{taw}]")
        if d["irrigation_required"] and not d["method"]:
            record("irrigation", label, "irrigate without method")
        if d["duration_hours"] is not None and d["duration_hours"] > 8.0 + 1e-6:
            record("irrigation", label, "duration over one working day")


async def sweep_irrigation(weather_outputs):
    weathers = {k: v for k, v in weather_outputs.items() if k.endswith("/normal")}
    weathers["none"] = {"forecast_short_term": [], "alerts": []}
    moistures = [0.0, 5.0, 15.0, 25.0, 40.0, 60.0, 100.0, None]
    for crop, soil in itertools.product(IRR_CROPS, IRR_SOILS):
        for wname in ("thar_heat/normal", "monsoon_deluge/normal", "ladakh_frost/normal", "none"):
            for moist in (moistures[i] for i in (0, 3, 5, 7)):
                label = f"{crop}/{soil}/{wname}/θ{moist}"
                RUNS["irrigation"] += 1
                payload = {"crop": crop, "soil_type": soil, "weather_data": weathers[wname],
                           "growth_stage": "flowering", "planning_horizon_days": 14}
                if moist is not None:
                    payload["soil_moisture_percent"] = moist
                try:
                    check_irrigation(label, await IRR.run(payload))
                except ValueError as exc:
                    record("irrigation", label, f"rejected valid input: {exc}")
                except Exception as exc:  # noqa: BLE001
                    record("irrigation", label, f"{type(exc).__name__}: {exc}")
    # odd but legal inputs
    odd = [
        {"crop": "mango", "days_after_sowing": 400},
        {"crop": "groundnut", "days_after_sowing": 0},
        {"crop": "groundnut", "days_after_sowing": 700},
        {"crop": "cotton", "sowing_date": (date.today() - timedelta(days=90)).isoformat()},
        {"crop": "potato", "water_ec_ds_m": 15.0},
        {"crop": "rice", "growth_stage": "panicle_initiation"},
        {"crop": "wheat", "irrigation_method": "center_pivot", "farm_area_hectares": 0.01},
        {"crop": "sugarcane", "farm_area_hectares": 5000},
        {"crop": "tomato", "electrical_conductivity": 16.0},
        {},
    ]
    for extra in odd:
        for method in list(METHODS)[:3]:
            label = f"odd/{extra}/{method}"
            RUNS["irrigation"] += 1
            payload = {"weather_data": weathers["thar_heat/normal"], "soil_type": "loamy",
                       "soil_moisture_percent": 15.0, "irrigation_method": method, **extra}
            try:
                check_irrigation(label, await IRR.run(payload))
            except Exception as exc:  # noqa: BLE001
                record("irrigation", label, f"{type(exc).__name__}: {exc}")


# ─────────────────────────────────────────────────────────────────────────────
# SOIL HEALTH
# ─────────────────────────────────────────────────────────────────────────────
from AI_Backend.agents.crop_planning_growth.soil_health.agent import SoilHealthAgent
from AI_Backend.agents.crop_planning_growth.soil_health.config import (
    CROP_CONFIG as SH_CROPS, SOIL_TYPE_CONFIG as SH_SOILS)
from AI_Backend.agents.crop_planning_growth.soil_health.schemas import SoilHealthOutput

SH = SoilHealthAgent()
EXTREMES = [
    dict(soil_ph=3.0, electrical_conductivity=0.0),
    dict(soil_ph=10.0, electrical_conductivity=16.0),
    dict(soil_ph=7.0, electrical_conductivity=0.5, soil_moisture=0.0),
    dict(soil_ph=7.0, electrical_conductivity=0.5, soil_moisture=100.0),
    dict(soil_ph=6.5, electrical_conductivity=0.4, soil_moisture=30, soil_temperature=-10,
         air_temperature=-20, air_humidity=0, rainfall=500, nitrogen=0, phosphorus=0, potassium=0),
    dict(soil_ph=8.9, electrical_conductivity=9.0, soil_moisture=45, soil_temperature=60,
         air_temperature=55, air_humidity=100, rainfall=0, nitrogen=1000, phosphorus=500,
         potassium=2000, fertilizer_type="urea"),
    dict(soil_ph=5.0, electrical_conductivity=3.0, soil_moisture=20, fertilizer_type="lime"),
]


def check_soil(label, out):
    strict_json(out)
    SoilHealthOutput.model_validate(out)
    if not 0 <= out["soil_health_score"] <= 100:
        record("soil", label, "score out of range")
    if not 0 <= out["data_quality_score"] <= 1:
        record("soil", label, "data quality out of range")


async def sweep_soil():
    for crop, soil, (i, ext) in itertools.product(list(SH_CROPS) + [None, "unknownplant"],
                                                   list(SH_SOILS) + [None, "Saline-Alkaline", "rock"],
                                                   enumerate(EXTREMES)):
        for source in ("sensor", "lab"):
            label = f"{crop}/{soil}/ext{i}/{source}"
            RUNS["soil"] += 1
            try:
                check_soil(label, await SH.run({**ext, "crop_type": crop, "soil_type": soil,
                                                "nutrient_source": source}))
            except Exception as exc:  # noqa: BLE001
                record("soil", label, f"{type(exc).__name__}: {exc}")


# ─────────────────────────────────────────────────────────────────────────────
# CROP PREDICTION (offline climate)
# ─────────────────────────────────────────────────────────────────────────────
from AI_Backend.agents.crop_planning_growth.crop_prediction import climate as cmod
from AI_Backend.agents.crop_planning_growth.crop_prediction.agent import CropPredictionAgent
from AI_Backend.agents.crop_planning_growth.crop_prediction.schemas import (
    CropPredictionResponse, SoilType, Month)

CROP = CropPredictionAgent()


def era5(rain_per_day, temp=28.0, rh=70.0):
    last = date.today().year - 1
    start = date(last - 9, 1, 1)
    n = (date(last, 12, 31) - start).days + 1
    return {"daily": {"time": [(start + timedelta(days=i)).isoformat() for i in range(n)],
                      "precipitation_sum": [rain_per_day] * n,
                      "temperature_2m_mean": [temp] * n, "relative_humidity_2m_mean": [rh] * n}}


def check_crop(label, r):
    d = r.model_dump(mode="json")
    strict_json(d)
    CropPredictionResponse.model_validate(d)
    for c in r.recommendations:
        if not 0 <= c.suitability_score <= 100:
            record("crop", label, "suitability out of range")
        w = c.agronomy.water_security if c.agronomy else None
        if w and not (0 <= w.rain_met_percent_median <= 100):
            record("crop", label, f"rain met {w.rain_met_percent_median}% out of range")


async def sweep_crop():
    climates = {"desert": era5(0.0, 35, 15), "flood": era5(30.0, 27, 95), "cold": era5(2.0, 3, 60)}
    for cname, payload in climates.items():
        cmod.clear_cache()
        CROP.service.climate_transport = httpx.MockTransport(lambda r, p=payload: httpx.Response(200, json=p))
        for soil, month in itertools.product(list(SoilType), list(Month)):
            for ph, ec, moist in ((3.0, 0.0, 0.0), (7.2, 0.5, 30.0), (10.0, 20.0, 100.0)):
                label = f"{cname}/{soil.value}/{month.value}/pH{ph}"
                RUNS["crop"] += 1
                try:
                    check_crop(label, await CROP.predict({
                        "ph": ph, "ec_ds_m": ec, "moisture_percent": moist,
                        "soil_type": soil.value, "month": month.value,
                        "location": {"lat": 23.0, "lon": 72.5}, "top_n": 5,
                        "previous_crops": ["Tomato", "cotton"], "irrigation_available": False,
                        "n_kg_ha": 0, "p_kg_ha": 0, "k_kg_ha": 0}))
                except Exception as exc:  # noqa: BLE001
                    record("crop", label, f"{type(exc).__name__}: {exc}")


# ─────────────────────────────────────────────────────────────────────────────
# CROSS-AGENT: names flowing between agents must be understood everywhere
# ─────────────────────────────────────────────────────────────────────────────
def cross_agent():
    from AI_Backend.agents.crop_planning_growth.soil_health.service import canonical_crop, canonical_soil
    from AI_Backend.agents.crop_planning_growth.irrigation_planner.service import IrrigationService
    from AI_Backend.ml.crop_prediction.recommend import _load_prepared

    crops = sorted({p["crop"] for p in _load_prepared()})
    for crop in crops:
        RUNS["cross"] += 1
        try:
            IrrigationService._resolve_crop(crop, [])
        except ValueError:
            record("cross", crop, "crop-agent crop unknown to irrigation")
        if canonical_crop(crop) is None:
            record("cross", crop, "crop-agent crop unknown to soil health")
    for soil in SoilType:
        RUNS["cross"] += 1
        try:
            IrrigationService._resolve_soil(soil.value, [])
        except ValueError:
            record("cross", soil.value, "crop-agent soil unknown to irrigation")
        if canonical_soil(soil.value) is None:
            record("cross", soil.value, "crop-agent soil unknown to soil health")


# ─────────────────────────────────────────────────────────────────────────────
# Agronomic rules at the edges
# ─────────────────────────────────────────────────────────────────────────────
def _days(tmin, tmax, n=3):
    return {"location": {"lat": 23.0, "lon": 72.5}, "forecast_short_term": [
        {"date": (date(2026, 9, 22) + timedelta(days=i)).isoformat(), "temp_min": tmin,
         "temp_max": tmax, "rainfall_mm": 0, "rain_probability_percent": 5, "humidity": 55,
         "wind_speed": 8, "et0_mm": 5.0} for i in range(n)]}


async def edge_rules():
    first = lambda p: p["irrigation_schedule"][0]
    checks = {}
    frozen = await IRR.run({"crop": "wheat", "soil_type": "loamy", "soil_moisture_percent": 12.0,
                            "growth_stage": "vegetative", "weather_data": _days(-18, -2)})
    checks["frozen ground is never irrigated"] = (
        first(frozen)["decision_code"] == "POSTPONE_FROZEN" and not first(frozen)["irrigation_required"])
    mature = await IRR.run({"crop": "groundnut", "soil_type": "loamy", "soil_moisture_percent": 14.0,
                            "growth_stage": "harvest_ready", "weather_data": _days(24, 34)})
    checks["maturing field crop dries down"] = first(mature)["decision_code"] == "SKIP_CROP_MATURE"
    picked = await IRR.run({"crop": "tomato", "soil_type": "loamy", "soil_moisture_percent": 14.0,
                            "growth_stage": "harvest_ready", "weather_data": _days(24, 34)})
    checks["continuously picked vegetable keeps irrigating"] = first(picked)["irrigation_required"]
    late = await IRR.run({"crop": "groundnut", "soil_type": "loamy", "soil_moisture_percent": 20.0,
                          "days_after_sowing": 700, "weather_data": _days(24, 34)})
    checks["sowing date far past the season is flagged"] = any(
        "past the ~130-day season" in w for w in late["warnings"])
    orchard = await IRR.run({"crop": "mango", "soil_type": "loamy", "soil_moisture_percent": 20.0,
                             "days_after_sowing": 400, "weather_data": _days(24, 34)})
    checks["perennial ignores days after sowing honestly"] = any(
        "perennial" in w for w in orchard["warnings"])

    lat, lon, off, tmin, tmax, rh, rain, wind = CLIMATES["ladakh_frost"]
    wsvc.clear_cache()
    cold = await weather_agent_for(om_payload(lat, off, tmin, tmax, rh, rain, wind)).run(
        {"lat": lat, "lon": lon})
    advisory = cold["agro_advisory"]
    checks["no spray windows below 5 C"] = (advisory["spray_windows"] == []
                                            and "below 5" in (advisory["spray_limiting_factor"] or ""))
    checks["frozen week says do not irrigate"] = any("frozen" in s for s in advisory["summary"]) and         not any("plan irrigation" in s for s in advisory["summary"])

    chilled = await SH.run({"soil_ph": 7.0, "electrical_conductivity": 0.5, "soil_temperature": -5})
    checks["frozen soil raises a soil-temperature alert"] = any(
        a["type"] == "LOW_SOIL_TEMP" for a in chilled["alerts"])
    cabbage = await IRR.run({"crop": "Cabbage", "soil_type": "loamy", "soil_moisture_percent": 20.0,
                             "growth_stage": "vegetative", "weather_data": _days(15, 25)})
    checks["cabbage is known downstream"] = cabbage["crop_profile"]["crop"] == "cabbage"
    for name, ok in checks.items():
        RUNS["edge"] += 1
        if not ok:
            record("edge", name, "rule violated")


async def run_all() -> bool:
    weather = await sweep_weather()
    await sweep_irrigation(weather)
    await sweep_soil()
    await sweep_crop()
    cross_agent()
    await edge_rules()
    total = sum(len(v) for v in FAIL.values())
    for agent, items in FAIL.items():
        for item in items[:10]:
            print(f"[FAIL] {agent}: {item}")
    print()
    print(f"{sum(RUNS.values())} scenario runs {dict(RUNS)}; {total} failures")
    return total == 0


if __name__ == "__main__":
    sys.exit(0 if asyncio.run(run_all()) else 1)
