"""Regression suite for the Weather Watcher agent.

Both providers are faked with httpx.MockTransport, so this runs offline with
no API key, and every failure mode can be staged exactly: a rejected key, an
outage, a malformed payload, a corrupt value, a slow retry.

    python -m AI_Backend.tests.test_weather_watcher

No pytest dependency on purpose - the backend does not ship one.
"""
from __future__ import annotations

import asyncio
import io
import json
import logging
import sys
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs

import httpx

from AI_Backend.agents.crop_planning_growth.weather_watcher import service as svc
from AI_Backend.agents.crop_planning_growth.weather_watcher.agent import WeatherAgent
from AI_Backend.agents.crop_planning_growth.weather_watcher.schemas import WeatherWatcherOutput

SECRET = "SECRET_KEY_do_not_leak_123"
IST = timezone(timedelta(hours=5, minutes=30))

# Retries must not slow the suite down.
svc.HTTP_BACKOFF_SECONDS = 0.0


# ---------------------------------------------------------------------------
# fake providers
# ---------------------------------------------------------------------------
def om_payload(overrides: dict | None = None, days: int = 14, current: bool = True) -> dict:
    """Open-Meteo daily payload starting at today's local date in IST."""
    today = datetime.now(IST).date()
    times = [(today + timedelta(days=i)).isoformat() for i in range(days)]
    daily = {
        "time": times,
        "temperature_2m_max": [34.0] * days,
        "temperature_2m_min": [24.0] * days,
        "precipitation_sum": [2.0] * days,
        "precipitation_probability_max": [30] * days,
        "wind_speed_10m_max": [12.0] * days,
        "relative_humidity_2m_mean": [60.0] * days,
    }
    for key, per_day in (overrides or {}).items():
        for index, value in per_day.items():
            daily[key][index] = value
    out = {"timezone": "Asia/Kolkata", "utc_offset_seconds": 19800, "daily": daily}
    if current:
        out["current"] = {"temperature_2m": 31.0, "relative_humidity_2m": 55,
                          "precipitation": 0.0, "wind_speed_10m": 9.0, "weather_code": 1}
    return out


def ow_current_payload(temp: float = 32.0) -> dict:
    return {"main": {"temp": temp, "humidity": 50}, "wind": {"speed": 3.0},
            "weather": [{"main": "Clear"}], "rain": {"1h": 0.4}}


def ow_forecast_payload() -> dict:
    """40 three-hour slots covering the rest of today, IST offset.

    Anchored to 12:00 on the farm's local day, not to "now". Anchoring to now
    made the suite depend on the hour it ran: just after local midnight the
    3-hourly feed covers nearly the whole local day, the agent rightly prefers
    it over the daily feed, and tests written around a partial first day
    failed for a correct reason. Starting at midday keeps today genuinely
    partial (4 slots, below MIN_SLOTS_FOR_FULL_DAY) at every hour of the day.
    """
    local_noon = datetime.now(IST).replace(hour=12, minute=0, second=0, microsecond=0)
    start = local_noon.astimezone(timezone.utc)
    slots = []
    for i in range(40):
        ts = start + timedelta(hours=3 * i)
        slots.append({"dt": int(ts.timestamp()),
                      "main": {"temp": 30.0, "temp_min": 25.0, "temp_max": 35.0, "humidity": 50},
                      "wind": {"speed": 4.0}, "pop": 0.2, "rain": {"3h": 1.0}})
    return {"city": {"timezone": 19800}, "list": slots}


class FakeProviders:
    """Routes by URL; each route is a callable(request) -> httpx.Response."""

    def __init__(self, **routes):
        self.routes = {"weather": lambda r: httpx.Response(200, json=ow_current_payload()),
                       "forecast": lambda r: httpx.Response(200, json=ow_forecast_payload()),
                       "open-meteo": lambda r: httpx.Response(200, json=om_payload())}
        self.routes.update(routes)
        self.calls: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if "open-meteo" in request.url.host:
            name = "open-meteo"
        elif request.url.path.endswith("/forecast"):
            name = "forecast"
        else:
            name = "weather"
        self.calls.append(name)
        return self.routes[name](request)

    def agent(self, api_key: str | None = SECRET) -> WeatherAgent:
        return WeatherAgent(api_key=api_key or "", transport=httpx.MockTransport(self))


def fresh() -> None:
    svc.clear_cache()


LAT, LON = 23.02, 72.57


# ---------------------------------------------------------------------------
# P0 - the bugs from the review
# ---------------------------------------------------------------------------
async def case_api_key_never_leaks_into_output_or_logs():
    fresh()
    providers = FakeProviders(weather=lambda r: httpx.Response(401, request=r),
                              forecast=lambda r: httpx.Response(401, request=r))
    agent = providers.agent()
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    agent.logger.addHandler(handler)
    previous_level = agent.logger.level
    agent.logger.setLevel(logging.DEBUG)   # the runner silences it; this check must see logs
    try:
        out = await agent.run({"lat": LAT, "lon": LON})
    finally:
        agent.logger.setLevel(previous_level)
        agent.logger.removeHandler(handler)
    body = json.dumps(out, default=str)
    logged = stream.getvalue()
    return (SECRET not in body and SECRET not in logged
            and "HTTP 401" in logged   # proves the failure was logged at all
            and any("rejected the API key (HTTP 401)" in w for w in out["warnings"]))


async def case_concurrent_requests_keep_their_own_warnings():
    fresh()

    def om(request):
        lat = float(parse_qs(request.url.query.decode())["latitude"][0])
        return httpx.Response(503) if lat < 15 else httpx.Response(200, json=om_payload())

    agent = FakeProviders(**{"open-meteo": om}).agent()
    bad, good = await asyncio.gather(agent.run({"lat": 10.0, "lon": 70.0}),
                                     agent.run({"lat": LAT, "lon": LON}))
    return (any("Open-Meteo" in w for w in bad["warnings"])
            and not any("Open-Meteo" in w for w in good["warnings"]))


async def case_forecast_days_are_full_local_calendar_days():
    fresh()
    out = await FakeProviders().agent().run({"lat": LAT, "lon": LON})
    days = out["forecast_short_term"] + out["forecast_long_term"]
    dates = [d["date"] for d in days]
    today = datetime.now(IST).date().isoformat()
    return (dates == sorted(dates) and len(dates) == len(set(dates))
            and dates[0] == today
            # today is partial in the 3-hourly feed, so it comes from Open-Meteo
            and days[0]["source"] == "open-meteo"
            and any(d["source"] == "openweather" for d in days)
            and len(out["forecast_short_term"]) == 7 and len(out["forecast_long_term"]) == 7)


async def case_rainfall_today_is_the_full_day_total():
    fresh()
    providers = FakeProviders(**{"open-meteo": lambda r: httpx.Response(
        200, json=om_payload({"precipitation_sum": {0: 38.0}}))})
    out = await providers.agent().run({"lat": LAT, "lon": LON})
    cw = out["current_weather"]
    return cw["rainfall_today"] == 38.0 and cw["rainfall_last_hour_mm"] == 0.4


async def case_malformed_payload_does_not_fail_the_request():
    fresh()
    providers = FakeProviders(**{"open-meteo": lambda r: httpx.Response(
        200, json={"daily": {"time": "not-a-list", "temperature_2m_max": None}})})
    out = await providers.agent().run({"lat": LAT, "lon": LON})
    return out["status"] == "partial" and out["current_weather"] is not None \
        and len(out["forecast_short_term"]) > 0


async def case_corrupt_values_are_dropped_not_passed_on():
    fresh()
    providers = FakeProviders(**{"open-meteo": lambda r: httpx.Response(
        200, json=om_payload({"temperature_2m_max": {9: 999.0}}))})
    out = await providers.agent().run({"lat": LAT, "lon": LON})
    days = out["forecast_short_term"] + out["forecast_long_term"]
    return (all(d["temp_max"] < 100 for d in days)
            and any("invalid values" in w for w in out["warnings"]))


# ---------------------------------------------------------------------------
# P1 - performance and resilience
# ---------------------------------------------------------------------------
async def case_providers_are_called_concurrently():
    fresh()

    async def slow(request):
        await asyncio.sleep(0.3)
        return FakeProviders()(request)

    class SlowTransport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request):
            return await slow(request)

    agent = WeatherAgent(api_key=SECRET, transport=SlowTransport())
    started = time.perf_counter()
    await agent.run({"lat": LAT, "lon": LON})
    elapsed = time.perf_counter() - started
    return elapsed < 0.6   # three 0.3 s calls in parallel, not 0.9 s in series


async def case_cache_serves_repeat_requests_without_calling_providers():
    fresh()
    providers = FakeProviders()
    agent = providers.agent()
    first = await agent.run({"lat": LAT, "lon": LON})
    calls_after_first = len(providers.calls)
    second = await agent.run({"lat": LAT + 0.001, "lon": LON})   # same ~1 km cell
    return (first["cached"] is False and second["cached"] is True
            and len(providers.calls) == calls_after_first == 3)


async def case_concurrent_requests_share_one_fetch():
    fresh()
    providers = FakeProviders()
    agent = providers.agent()
    await asyncio.gather(*[agent.run({"lat": LAT, "lon": LON}) for _ in range(10)])
    return len(providers.calls) == 3


async def case_transient_errors_are_retried():
    fresh()
    attempts = {"n": 0}

    def flaky(request):
        attempts["n"] += 1
        return httpx.Response(503) if attempts["n"] == 1 else httpx.Response(200, json=om_payload())

    out = await FakeProviders(**{"open-meteo": flaky}).agent().run({"lat": LAT, "lon": LON})
    return attempts["n"] == 2 and out["sources"]["open_meteo"] == "ok"


async def case_rejected_key_is_not_retried():
    fresh()
    providers = FakeProviders(weather=lambda r: httpx.Response(401),
                              forecast=lambda r: httpx.Response(401))
    await providers.agent().run({"lat": LAT, "lon": LON})
    return providers.calls.count("weather") == 1 and providers.calls.count("forecast") == 1


async def case_runs_on_open_meteo_alone_without_a_key():
    fresh()
    providers = FakeProviders()
    out = await providers.agent(api_key=None).run({"lat": LAT, "lon": LON})
    return (out["status"] == "ok" and providers.calls == ["open-meteo"]
            and out["current_weather"]["source"] == "open-meteo"
            and len(out["forecast_short_term"]) == 7
            and out["sources"]["openweather_current"] == "skipped")


async def case_total_outage_is_unavailable_not_empty_ok():
    fresh()
    down = lambda r: httpx.Response(503)
    out = await FakeProviders(weather=down, forecast=down, **{"open-meteo": down}
                              ).agent().run({"lat": LAT, "lon": LON})
    return (out["status"] == "unavailable" and out["current_weather"] is None
            and out["forecast_short_term"] == [])


async def case_outage_serves_recent_forecast_with_its_age():
    fresh()
    good = FakeProviders()
    await good.agent().run({"lat": LAT, "lon": LON})
    # Age the cache entry past its TTL but within the stale window.
    for key, (stored_at, value) in list(svc._cache._data.items()):
        svc._cache._data[key] = (stored_at - svc.CACHE_TTL_SECONDS - 600, value)
    down = lambda r: httpx.Response(503)
    out = await FakeProviders(weather=down, forecast=down, **{"open-meteo": down}
                              ).agent().run({"lat": LAT, "lon": LON})
    return (out["status"] == "partial" and out["cached"] is True
            and len(out["forecast_short_term"]) == 7
            and any("minutes ago" in w for w in out["warnings"]))


# ---------------------------------------------------------------------------
# P2 - alerts follow published thresholds
# ---------------------------------------------------------------------------
def alerts_for(days_override: dict, current_temp: float = 30.0) -> list[dict]:
    fresh()
    providers = FakeProviders(
        weather=lambda r: httpx.Response(200, json=ow_current_payload(current_temp)),
        **{"open-meteo": lambda r: httpx.Response(200, json=om_payload(days_override))})
    out = asyncio.run(providers.agent(api_key=None).run({"lat": LAT, "lon": LON}))
    return out["alerts"]


def types_on(alerts: list[dict], day_index: int) -> dict:
    day = (datetime.now(IST).date() + timedelta(days=day_index)).isoformat()
    return {a["type"]: a["severity"] for a in alerts if a["date"] == day}


def case_heat_thresholds_follow_imd():
    alerts = alerts_for({"temperature_2m_max": {2: 41.0, 3: 44.9, 4: 45.5, 5: 47.5}})
    return (types_on(alerts, 2) == {"heat_stress": "medium"}
            and types_on(alerts, 3) == {"heat_stress": "medium"}   # not a heat wave
            and types_on(alerts, 4) == {"heatwave": "high"}
            and types_on(alerts, 5) == {"heatwave": "critical"})


def case_cold_thresholds_frost_is_not_five_degrees():
    alerts = alerts_for({"temperature_2m_min": {2: 5.0, 3: 3.5, 4: 1.5, 5: -1.0}})
    return (types_on(alerts, 2) == {}
            and types_on(alerts, 3) == {"cold_wave": "medium"}
            and types_on(alerts, 4) == {"frost": "high"}          # supersedes cold wave
            and types_on(alerts, 5) == {"frost": "critical"})


def case_rain_thresholds_follow_imd_categories():
    alerts = alerts_for({"precipitation_sum": {2: 50.0, 3: 70.0, 4: 130.0, 5: 210.0}})
    return (types_on(alerts, 2) == {}
            and types_on(alerts, 3) == {"heavy_rainfall": "high"}
            and types_on(alerts, 4) == {"heavy_rainfall": "critical"}
            and types_on(alerts, 5) == {"heavy_rainfall": "critical"})


def case_high_humidity_raises_disease_advisory():
    alerts = alerts_for({"relative_humidity_2m_mean": {3: 90.0}})
    return types_on(alerts, 3) == {"high_humidity": "medium"}


async def case_hazard_from_either_model_is_not_lost():
    """OpenWeather shows 8 mm on day 1, Open-Meteo 80 mm: the farmer is warned."""
    fresh()
    out = await FakeProviders(**{"open-meteo": lambda r: httpx.Response(
        200, json=om_payload({"precipitation_sum": {1: 80.0}}))}).agent().run(
        {"lat": LAT, "lon": LON})
    day1 = (datetime.now(IST).date() + timedelta(days=1)).isoformat()
    shown = next(d for d in out["forecast_short_term"] if d["date"] == day1)
    alert = next((a for a in out["alerts"]
                  if a["type"] == "heavy_rainfall" and a["date"] == day1), None)
    return (shown["source"] == "openweather" and shown["rainfall_mm"] < 64.5
            and shown["storm_warning"] is True            # flag raised by the other model
            and alert is not None and "one forecast model" in alert["message"])


def case_one_alert_per_type_and_day():
    """Current reading and today's forecast both hot: one alert, the worse one."""
    alerts = alerts_for({"temperature_2m_max": {0: 46.0}}, current_temp=41.0)
    today = types_on(alerts, 0)
    return today == {"heatwave": "high"}


# ---------------------------------------------------------------------------
# P3 - contract and consumers
# ---------------------------------------------------------------------------
async def case_output_validates_against_schema():
    fresh()
    out = await FakeProviders().agent().run({"lat": LAT, "lon": LON})
    WeatherWatcherOutput.model_validate(out)
    return True


async def case_invalid_locations_are_rejected_without_calling_providers():
    fresh()
    providers = FakeProviders()
    agent = providers.agent()
    results = [await agent.run(x) for x in (
        {"lat": float("nan"), "lon": 72.0}, {"lat": 95.0, "lon": 72.0},
        {"lat": "abc", "lon": 72.0}, {}, None)]
    return (all(r["status"] == "unavailable" for r in results)
            and providers.calls == [])


async def case_accepts_orchestrator_and_scheduler_shapes():
    fresh()
    agent = FakeProviders().agent()
    a = await agent.run({"location": {"lat": LAT, "lon": LON}})
    b = await agent.run({"farm": {"location": {"lat": LAT, "lon": LON}}})
    return a["status"] == b["status"] == "ok"


async def case_scheduler_adapter_accepts_the_output():
    from AI_Backend.agents.farm_operations_automation.task_scheduler.schemas import (
        WeatherAgentData)
    from AI_Backend.agents.farm_operations_automation.task_scheduler.adapters import weather_output_to_scheduler_block

    fresh()
    out = await FakeProviders(**{"open-meteo": lambda r: httpx.Response(
        200, json=om_payload({"precipitation_sum": {1: 80.0}}))}).agent().run(
        {"lat": LAT, "lon": LON})
    block = weather_output_to_scheduler_block(out)
    data = WeatherAgentData.model_validate(block)
    return (len(data.forecast) > 0
            and any(a.type == "heavy_rainfall" for a in data.alerts))


async def case_crop_agent_uses_the_full_fourteen_days():
    from AI_Backend.agents.crop_planning_growth.crop_prediction.agent import (
        CropPredictionAgent)

    fresh()
    weather = await FakeProviders().agent().run({"lat": LAT, "lon": LON})
    r = await CropPredictionAgent().predict({
        "ph": 7.8, "ec_ds_m": 0.5, "moisture_percent": 30.0,
        "soil_type": "Black Cotton", "month": "June", "region": "Gujarat",
        "weather_data": weather})
    return any("14-day forecast mean" in w for w in r.warnings) and \
        any("Humidity taken from the 14-day" in w for w in r.warnings)


def case_router_returns_422_and_503():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from AI_Backend.routers import weather_watcher as router_module

    fresh()
    down = lambda r: httpx.Response(503)
    original = router_module.weather_agent
    router_module.weather_agent = FakeProviders(
        weather=down, forecast=down, **{"open-meteo": down}).agent()
    try:
        app = FastAPI()
        app.include_router(router_module.router)
        client = TestClient(app)
        bad = client.get("/weather-watcher/", params={"lat": 200, "lon": 72})
        outage = client.get("/weather-watcher/", params={"lat": LAT, "lon": LON})
        health = client.get("/weather-watcher/health").json()
    finally:
        router_module.weather_agent = original
    return (bad.status_code == 422 and outage.status_code == 503
            and SECRET not in json.dumps(health)
            and health["openweather_configured"] is True)


# ---------------------------------------------------------------------------
# Agrometeorology - formulas against published references
# ---------------------------------------------------------------------------
from AI_Backend.agents.crop_planning_growth.weather_watcher import agromet  # noqa: E402


def case_wet_bulb_matches_stull_2011():
    return abs(agromet.wet_bulb_c(20.0, 50.0) - 13.7) < 0.05


def case_heat_index_matches_nws_table():
    f_to_c = lambda f: (f - 32) * 5 / 9
    table = [(90, 70, 106), (100, 40, 109), (86, 90, 105), (104, 55, 137), (80, 40, 80)]
    return all(abs(agromet.heat_index_c(f_to_c(t), rh) * 9 / 5 + 32 - ref) <= 1.0
               for t, rh, ref in table)


def case_gdd_and_confidence():
    return (agromet.growing_degree_days(20.0, 30.0) == 15.0
            and agromet.growing_degree_days(2.0, 8.0) == 0.0
            and [agromet.forecast_confidence(i) for i in (0, 2, 3, 6, 7, 13)]
            == ["high", "high", "medium", "medium", "low", "low"])


# ---------------------------------------------------------------------------
# Agrometeorology - decisions on synthetic weather with a known answer
# ---------------------------------------------------------------------------
def synthetic_hours(start: datetime, n: int, **fixed) -> list[dict]:
    base = {"temp": 24.0, "rh": 55.0, "precip": 0.0, "pop": 5.0, "wind": 8.0}
    base.update(fixed)
    return [{"time": start + timedelta(hours=i), "is_day": 6 <= (start + timedelta(hours=i)).hour < 19,
             **base} for i in range(n)]


def case_spray_window_found_where_conditions_allow():
    now = datetime(2026, 9, 22, 5, 0)
    hours = synthetic_hours(now, 80, wind=22.0)            # too windy all the time...
    for h in hours:
        if h["time"].date() == now.date() and 7 <= h["time"].hour < 10:
            h["wind"] = 8.0                                # ...except 07-10 today
    windows, limiting = agromet.spray_windows(hours, now)
    return (len(windows) == 1 and windows[0]["start"] == "2026-09-22T07:00"
            and windows[0]["end"] == "2026-09-22T10:00" and windows[0]["hours"] == 3)


def case_spray_needs_a_rain_free_period_after():
    now = datetime(2026, 9, 22, 5, 0)
    hours = synthetic_hours(now, 80)
    for h in hours:
        if h["time"].hour == 12:
            h["precip"] = 3.0                              # rain at noon every day
    windows, _ = agromet.spray_windows(hours, now)
    # Rain at 12:00 blocks 12:00 itself and the four hours before it (08-11),
    # because spray needs 4 dry hours to become rainfast. Daylight is 06-19.
    tomorrow = [(w["start"][11:16], w["end"][11:16]) for w in windows
                if w["date"] == "2026-09-23"]
    return tomorrow == [("06:00", "08:00"), ("13:00", "19:00")]


def case_hot_dry_air_blocks_spraying_and_says_why():
    now = datetime(2026, 5, 10, 5, 0)
    hours = synthetic_hours(now, 80, temp=42.0, rh=15.0)   # Delta-T ~ 18 C
    windows, limiting = agromet.spray_windows(hours, now)
    return windows == [] and "Delta-T above" in (limiting or "")


def case_night_hours_are_never_spray_windows():
    now = datetime(2026, 9, 22, 0, 0)
    windows, _ = agromet.spray_windows(synthetic_hours(now, 80), now)
    return windows and all(6 <= int(w["start"][11:13]) and int(w["end"][11:13]) <= 19
                           for w in windows)


def case_hutton_needs_two_consecutive_qualifying_days():
    start = datetime(2026, 9, 22, 0, 0)
    hours = synthetic_hours(start, 24 * 5, temp=18.0, rh=70.0)
    for h in hours:
        day = (h["time"] - start).days
        if day in (1, 2, 4) and h["time"].hour < 8:       # 8 humid hours on days 1, 2, 4
            h["rh"] = 95.0
    stats = agromet.daily_hourly_stats(hours)
    # Day 2 completes a period (1 and 2 qualify); day 4 alone does not.
    return agromet.hutton_dates(stats) == ["2026-09-24"]


def case_hutton_needs_warm_nights():
    start = datetime(2026, 12, 1, 0, 0)
    hours = synthetic_hours(start, 48, temp=8.0, rh=95.0)  # wet but Tmin < 10 C
    return agromet.hutton_dates(agromet.daily_hourly_stats(hours)) == []


def case_fungal_risk_needs_wetness_at_the_right_temperature():
    start = datetime(2026, 9, 22, 0, 0)
    warm_wet = synthetic_hours(start, 24, temp=22.0, rh=95.0)
    hot_wet = synthetic_hours(start, 24, temp=34.0, rh=95.0)
    s1 = agromet.daily_hourly_stats(warm_wet)["2026-09-22"]
    s2 = agromet.daily_hourly_stats(hot_wet)["2026-09-22"]
    return (agromet.fungal_risk(s1["favourable_wet_hours"]) == "high"
            and agromet.fungal_risk(s2["favourable_wet_hours"]) == "low")


def case_water_balance_classifies_demand():
    days = [{"rainfall_mm": 1.0, "et0_mm": 5.0} for _ in range(7)]
    dry = agromet.water_balance(days)
    wet = agromet.water_balance([{"rainfall_mm": 9.0, "et0_mm": 5.0} for _ in range(7)])
    return (dry["status"] == "irrigation_likely_needed" and dry["rain_covers_percent"] == 20
            and dry["balance_mm"] == -28.0 and wet["status"] == "rain_covers_demand")


def case_dry_spells_found():
    days = [{"date": f"2026-09-{22 + i}", "rainfall_mm": r, "rain_probability_percent": p}
            for i, (r, p) in enumerate([(0, 10), (0, 10), (0, 10), (12, 80), (0, 5), (0.5, 20)])]
    return agromet.dry_spells(days) == [
        {"start": "2026-09-22", "end": "2026-09-24", "days": 3},
        {"start": "2026-09-26", "end": "2026-09-27", "days": 2}]


# ---------------------------------------------------------------------------
# Agrometeorology - end to end through the agent and the API
# ---------------------------------------------------------------------------
def om_with_hourly(hour_fn=None, et0: float = 5.0, **daily_overrides) -> dict:
    """Open-Meteo payload including the hourly series and daily ET0."""
    payload = om_payload(daily_overrides or None)
    start = datetime.combine(datetime.now(IST).date(), datetime.min.time())
    times, cols = [], {k: [] for k in ("temperature_2m", "relative_humidity_2m", "precipitation",
                                        "precipitation_probability", "wind_speed_10m", "is_day")}
    for i in range(14 * 24):
        t = start + timedelta(hours=i)
        v = {"temp": 22.0 + 8.0 * (1 if 10 <= t.hour <= 16 else 0), "rh": 60.0,
             "precip": 0.0, "pop": 10.0, "wind": 8.0}
        if hour_fn:
            v.update(hour_fn(i // 24, t.hour) or {})
        times.append(t.isoformat(timespec="minutes"))
        cols["temperature_2m"].append(v["temp"])
        cols["relative_humidity_2m"].append(v["rh"])
        cols["precipitation"].append(v["precip"])
        cols["precipitation_probability"].append(v["pop"])
        cols["wind_speed_10m"].append(v["wind"])
        cols["is_day"].append(1 if 6 <= t.hour < 19 else 0)
    payload["hourly"] = {"time": times, **cols}
    payload["daily"]["et0_fao_evapotranspiration"] = [et0] * 14
    return payload


async def case_advisory_reaches_the_farmer_end_to_end():
    fresh()
    out = await FakeProviders(**{"open-meteo": lambda r: httpx.Response(
        200, json=om_with_hourly(et0=5.0))}).agent(api_key=None).run({"lat": LAT, "lon": LON})
    adv = out["agro_advisory"]
    day0 = out["forecast_short_term"][0]
    WeatherWatcherOutput.model_validate(out)
    return (adv["hourly_available"] is True
            and adv["water_balance_7d"]["status"] == "irrigation_likely_needed"   # 2 mm vs 5 mm
            and any("plan irrigation" in line for line in adv["summary"])
            and day0["et0_mm"] == 5.0 and day0["forecast_confidence"] == "high"
            and day0["gdd_base10"] == 19.0 and "leaf_wetness_hours" in day0)


async def case_late_blight_alert_raised_for_potato_weather():
    fresh()

    def blight_weather(day, hour):
        if day in (2, 3):
            return {"temp": 16.0, "rh": 95.0 if hour < 9 else 80.0}
        return None

    out = await FakeProviders(**{"open-meteo": lambda r: httpx.Response(
        200, json=om_with_hourly(blight_weather))}).agent(api_key=None).run({"lat": LAT, "lon": LON})
    day3 = (datetime.now(IST).date() + timedelta(days=3)).isoformat()
    return any(a["type"] == "late_blight_risk" and a["date"] == day3 for a in out["alerts"]) \
        and any("Late blight" in line for line in out["agro_advisory"]["summary"])


async def case_leaf_wetness_replaces_crude_humidity_alert():
    """With hourly data, disease advice comes from leaf wetness, not a daily mean."""
    fresh()
    out = await FakeProviders(**{"open-meteo": lambda r: httpx.Response(
        200, json=om_with_hourly(relative_humidity_2m_mean={3: 92.0}))}).agent(
        api_key=None).run({"lat": LAT, "lon": LON})
    return not any(a["type"] == "high_humidity" for a in out["alerts"])


async def case_dangerous_heat_index_warns_about_workers():
    fresh()
    hot = lambda day, hour: {"temp": 40.0, "rh": 50.0} if day == 1 and 11 <= hour <= 15 else None
    out = await FakeProviders(**{"open-meteo": lambda r: httpx.Response(
        200, json=om_with_hourly(hot))}).agent(api_key=None).run({"lat": LAT, "lon": LON})
    day1 = (datetime.now(IST).date() + timedelta(days=1)).isoformat()
    return any(a["type"] == "heat_safety" and a["date"] == day1 for a in out["alerts"])


def case_cached_result_drops_spray_windows_that_ended():
    from AI_Backend.agents.crop_planning_growth.weather_watcher.service import (
        _drop_expired_spray_windows)
    now = (datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)).replace(tzinfo=None)
    past = {"end": (now - timedelta(hours=1)).isoformat(timespec="minutes")}
    future = {"end": (now + timedelta(hours=2)).isoformat(timespec="minutes")}
    result = {"utc_offset_seconds": 19800, "agro_advisory": {"spray_windows": [past, future]}}
    _drop_expired_spray_windows(result)
    return result["agro_advisory"]["spray_windows"] == [future]


def case_api_response_keeps_the_advisory():
    """response_model strips undeclared fields - the advisory must survive it."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from AI_Backend.routers import weather_watcher as router_module

    fresh()
    original = router_module.weather_agent
    router_module.weather_agent = FakeProviders(**{"open-meteo": lambda r: httpx.Response(
        200, json=om_with_hourly())}).agent(api_key=None)
    try:
        app = FastAPI()
        app.include_router(router_module.router)
        body = TestClient(app).get("/weather-watcher/", params={"lat": LAT, "lon": LON}).json()
    finally:
        router_module.weather_agent = original
    day0 = body["forecast_short_term"][0]
    return (body["agro_advisory"]["summary"]
            and body["agro_advisory"]["water_balance_7d"] is not None
            and day0["et0_mm"] is not None and day0["fungal_risk"] is not None)


CASES = [
    case_api_key_never_leaks_into_output_or_logs,
    case_concurrent_requests_keep_their_own_warnings,
    case_forecast_days_are_full_local_calendar_days,
    case_rainfall_today_is_the_full_day_total,
    case_malformed_payload_does_not_fail_the_request,
    case_corrupt_values_are_dropped_not_passed_on,
    case_providers_are_called_concurrently,
    case_cache_serves_repeat_requests_without_calling_providers,
    case_concurrent_requests_share_one_fetch,
    case_transient_errors_are_retried,
    case_rejected_key_is_not_retried,
    case_runs_on_open_meteo_alone_without_a_key,
    case_total_outage_is_unavailable_not_empty_ok,
    case_outage_serves_recent_forecast_with_its_age,
    case_heat_thresholds_follow_imd,
    case_cold_thresholds_frost_is_not_five_degrees,
    case_rain_thresholds_follow_imd_categories,
    case_high_humidity_raises_disease_advisory,
    case_hazard_from_either_model_is_not_lost,
    case_one_alert_per_type_and_day,
    case_output_validates_against_schema,
    case_invalid_locations_are_rejected_without_calling_providers,
    case_accepts_orchestrator_and_scheduler_shapes,
    case_scheduler_adapter_accepts_the_output,
    case_crop_agent_uses_the_full_fourteen_days,
    case_router_returns_422_and_503,
    case_wet_bulb_matches_stull_2011,
    case_heat_index_matches_nws_table,
    case_gdd_and_confidence,
    case_spray_window_found_where_conditions_allow,
    case_spray_needs_a_rain_free_period_after,
    case_hot_dry_air_blocks_spraying_and_says_why,
    case_night_hours_are_never_spray_windows,
    case_hutton_needs_two_consecutive_qualifying_days,
    case_hutton_needs_warm_nights,
    case_fungal_risk_needs_wetness_at_the_right_temperature,
    case_water_balance_classifies_demand,
    case_dry_spells_found,
    case_advisory_reaches_the_farmer_end_to_end,
    case_late_blight_alert_raised_for_potato_weather,
    case_leaf_wetness_replaces_crude_humidity_alert,
    case_dangerous_heat_index_warns_about_workers,
    case_cached_result_drops_spray_windows_that_ended,
    case_api_response_keeps_the_advisory,
]


def main() -> bool:
    logging.getLogger("WeatherWatcher").setLevel(logging.CRITICAL)
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
