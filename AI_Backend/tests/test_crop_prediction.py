"""Regression suite for the crop prediction agent.

Two kinds of check live here and both matter:

  * agronomic - the cases from the model repo's sanity suite, run through the
    agent rather than the engine, so a serving-layer bug that drops the veto
    or mangles a unit is caught here and not in the field;
  * contract - the boundary rejects what it should and the refusal path maps
    to the API shape without leaking `closest` into `recommendations`.

Accuracy metrics cannot see any of this. Run it before and after any change:

    python -m AI_Backend.tests.test_crop_prediction

No pytest dependency on purpose - the backend does not ship one.
"""
from __future__ import annotations

import asyncio
import sys

from pydantic import ValidationError

from AI_Backend.agents.crop_planning_growth.crop_prediction.agent import CropPredictionAgent
from AI_Backend.agents.crop_planning_growth.crop_prediction.model_loader import (
    UnknownRegionError,
    loaded_regions,
)
from AI_Backend.agents.crop_planning_growth.crop_prediction.schemas import (
    CropPredictionRequest,
    PredictionStatus,
)
from AI_Backend.agents.crop_planning_growth.crop_prediction.service import clear_cache

AGENT = CropPredictionAgent()


# ---------------------------------------------------------------------------
# Offline climate: a fake ERA5 archive with a known, controllable climate
# ---------------------------------------------------------------------------
import httpx  # noqa: E402

from AI_Backend.agents.crop_planning_growth.crop_prediction import climate as climate_mod  # noqa: E402

CLIMATE_RAIN = {"monsoon_mm_per_day": 7.0, "dry_mm_per_day": 0.1, "year_factors": None}


def era5_payload() -> dict:
    """Ten complete years: monsoon rain Jun-Sep, near-dry otherwise."""
    from datetime import date as _date, timedelta as _td
    last = _date.today().year - 1
    start = _date(last - 9, 1, 1)
    days = (_date(last, 12, 31) - start).days + 1
    factors = CLIMATE_RAIN["year_factors"] or [1.0] * 10
    times, rain, temp, rh = [], [], [], []
    for i in range(days):
        d = start + _td(days=i)
        wet = 6 <= d.month <= 9
        base = CLIMATE_RAIN["monsoon_mm_per_day"] if wet else CLIMATE_RAIN["dry_mm_per_day"]
        times.append(d.isoformat())
        rain.append(round(base * factors[(d.year - start.year) % len(factors)], 2))
        temp.append(29.0 if wet else 24.0)
        rh.append(78.0 if wet else 45.0)
    return {"daily": {"time": times, "precipitation_sum": rain,
                      "temperature_2m_mean": temp, "relative_humidity_2m_mean": rh}}


def fake_era5(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json=era5_payload())


AGENT.service.climate_transport = httpx.MockTransport(fake_era5)


def reset_climate(**overrides):
    CLIMATE_RAIN.update({"monsoon_mm_per_day": 7.0, "dry_mm_per_day": 0.1,
                         "year_factors": None, **overrides})
    climate_mod.clear_cache()

BASE = dict(soil_type="Loam", month="November", moisture_percent=25.0)


async def predict(**overrides):
    payload = {**BASE, **overrides}
    payload.setdefault("region", "Gujarat")
    return await AGENT.predict(payload)


def crops(response):
    return [c.crop for c in response.recommendations]


# ---------------------------------------------------------------------------
# agronomic behaviour
# ---------------------------------------------------------------------------
async def case_saline_wasteland_is_refused():
    r = await predict(ph=9.6, ec_ds_m=8.5, moisture_percent=5.0,
                      soil_type="Saline-Alkaline", month="January",
                      forecast_temp_mean_c=47.0, forecast_humidity_mean_percent=12.0,
                      forecast_rain_mm=5, region=None)
    return r.status is PredictionStatus.NO_SUITABLE_CROP and bool(r.message)


async def case_extreme_heat_is_refused():
    r = await predict(ph=7.0, ec_ds_m=0.4, month="May", forecast_temp_mean_c=58.0,
                      forecast_humidity_mean_percent=10.0, forecast_rain_mm=0,
                      region=None)
    return r.status is PredictionStatus.NO_SUITABLE_CROP


async def case_black_cotton_june_suggests_cotton():
    r = await predict(ph=7.8, ec_ds_m=0.5, soil_type="Black Cotton", month="June",
                      forecast_temp_mean_c=30.0, forecast_humidity_mean_percent=60.0,
                      forecast_rain_mm=700, region=None)
    return r.status is PredictionStatus.OK and "Cotton" in crops(r)[:3]


async def case_cool_rabi_loam_avoids_kharif_cotton():
    r = await predict(ph=6.8, ec_ds_m=0.3, forecast_temp_mean_c=20.0,
                      forecast_humidity_mean_percent=70.0, forecast_rain_mm=250,
                      region=None)
    return r.status is PredictionStatus.OK and "Cotton" not in crops(r)[:3]


async def case_every_recommendation_carries_reasons():
    r = await predict(ph=6.8, ec_ds_m=0.3, forecast_temp_mean_c=20.0,
                      forecast_humidity_mean_percent=70.0, forecast_rain_mm=250,
                      region=None)
    return r.status is PredictionStatus.OK and all(c.reasons for c in r.recommendations)


async def case_gujarat_filter_excludes_cabbage():
    r = await predict(ph=6.8, ec_ds_m=0.3, forecast_temp_mean_c=20.0,
                      forecast_humidity_mean_percent=70.0, forecast_rain_mm=250,
                      top_n=5)
    return "Cabbage" not in crops(r)


async def case_gujarat_returns_local_cultivars():
    r = await predict(ph=8.0, ec_us_cm=580, soil_type="Black Cotton", month="June",
                      forecast_temp_mean_c=30.7, forecast_humidity_mean_percent=55.0,
                      forecast_rain_mm=620)
    return any(v.variety.startswith(("G.Cot", "GG", "Girnar", "Gujarat"))
               for c in r.recommendations for v in c.top_varieties)


# ---------------------------------------------------------------------------
# unit handling - the integration bug that fails silently
# ---------------------------------------------------------------------------
async def case_ec_units_agree():
    """580 uS/cm and 0.58 dS/m are the same field and must score the same."""
    a = await predict(ph=8.0, ec_us_cm=580, soil_type="Black Cotton", month="June",
                      forecast_temp_mean_c=30.7, forecast_humidity_mean_percent=55.0,
                      forecast_rain_mm=620)
    b = await predict(ph=8.0, ec_ds_m=0.58, soil_type="Black Cotton", month="June",
                      forecast_temp_mean_c=30.7, forecast_humidity_mean_percent=55.0,
                      forecast_rain_mm=620)
    return crops(a) == crops(b) and a.recommendations[0].suitability_score == \
        b.recommendations[0].suitability_score


def case_ec_must_be_named_once():
    """Both units, or neither, is a caller bug and must not be guessed at."""
    for kwargs in ({}, {"ec_ds_m": 0.58, "ec_us_cm": 580}):
        try:
            CropPredictionRequest(ph=7.0, **BASE, **kwargs)
            return False
        except ValidationError:
            continue
    return True


def case_raw_sensor_ec_in_wrong_field_is_rejected():
    """580 sent as dS/m is a unit error, not a salt pan: reject, do not score."""
    try:
        CropPredictionRequest(ph=7.0, ec_ds_m=580, **BASE)
        return False
    except ValidationError:
        return True


def case_impossible_ph_is_rejected():
    try:
        CropPredictionRequest(ph=14.0, ec_ds_m=0.5, **BASE)
        return False
    except ValidationError:
        return True


def case_unknown_soil_type_is_rejected():
    try:
        CropPredictionRequest(ph=7.0, ec_ds_m=0.5, moisture_percent=25.0,
                              soil_type="loamy", month="November")
        return False
    except ValidationError:
        return True


def case_abbreviated_month_is_rejected():
    try:
        CropPredictionRequest(ph=7.0, ec_ds_m=0.5, moisture_percent=25.0,
                              soil_type="Loam", month="Nov")
        return False
    except ValidationError:
        return True


# ---------------------------------------------------------------------------
# API contract
# ---------------------------------------------------------------------------
async def case_refusal_keeps_closest_out_of_recommendations():
    r = await predict(ph=9.6, ec_ds_m=8.5, moisture_percent=5.0,
                      soil_type="Saline-Alkaline", month="January",
                      forecast_temp_mean_c=47.0, forecast_humidity_mean_percent=12.0,
                      forecast_rain_mm=5, region=None)
    return (r.status is PredictionStatus.NO_SUITABLE_CROP
            and r.recommendations == []
            and r.closest is not None
            and r.closest.rank == 0)


async def case_top_n_is_honoured():
    r = await predict(ph=6.8, ec_ds_m=0.3, forecast_temp_mean_c=20.0,
                      forecast_humidity_mean_percent=70.0, forecast_rain_mm=250,
                      top_n=3)
    return len(r.recommendations) <= 3 and [c.rank for c in r.recommendations] == \
        list(range(1, len(r.recommendations) + 1))


async def case_npk_advises_but_never_changes_the_ranking():
    field = dict(ph=6.8, ec_ds_m=0.3, forecast_temp_mean_c=20.0,
                 forecast_humidity_mean_percent=70.0, forecast_rain_mm=250)
    without = await predict(**field)
    with_npk = await predict(**field, n_kg_ha=150, p_kg_ha=45, k_kg_ha=210)
    return ([(c.crop, c.suitability_score, c.confidence) for c in without.recommendations]
            == [(c.crop, c.suitability_score, c.confidence) for c in with_npk.recommendations]
            and all(c.agronomy and c.agronomy.soil_nutrients for c in with_npk.recommendations)
            and any("not part of the suitability score" in w for w in with_npk.warnings))


async def case_problems_surface_failing_checks():
    r = await predict(ph=8.0, ec_us_cm=580, moisture_percent=51.2,
                      soil_type="Black Cotton", month="June",
                      forecast_temp_mean_c=30.7, forecast_humidity_mean_percent=55.0,
                      forecast_rain_mm=620)
    top = r.recommendations[0]
    return all(p in [x.detail for x in top.reasons] for p in top.problems) and \
        all(x.is_problem for x in top.reasons if x.score < 0.5)


async def case_response_is_json_serialisable():
    r = await predict(ph=8.0, ec_us_cm=580, soil_type="Black Cotton", month="June",
                      forecast_temp_mean_c=30.7, forecast_humidity_mean_percent=55.0,
                      forecast_rain_mm=620)
    payload = r.model_dump(mode="json")
    return payload["status"] == "ok" and payload["model_info"]["top3_accuracy"] == 0.99


async def case_orchestrator_run_reports_invalid_input():
    out = await AGENT.run({"ph": 7.0, "soil_type": "Loam", "month": "November"})
    block = out["crop_recommendation"]
    return (set(out) == {"crop_recommendation"}
            and block["agent_status"] == "invalid_input"
            and block["result"] is None and "moisture_percent" in block["error"])


async def case_orchestrator_run_returns_dict():
    out = await AGENT.run({
        "ph": 8.0, "ec_us_cm": 580, "moisture_percent": 51.2,
        "soil_type": "Black Cotton", "month": "June",
        "forecast_temp_mean_c": 30.7, "forecast_humidity_mean_percent": 55.0,
        "forecast_rain_mm": 620,
    })
    block = out["crop_recommendation"]
    return block["agent_status"] == "success" and block["result"]["status"] == "ok"


# ---------------------------------------------------------------------------
# one agent, every caller shape - what the old crop selector accepted
# ---------------------------------------------------------------------------
async def case_result_survives_the_langgraph_state():
    """LangGraph drops any key a node returns that the state does not declare.

    Runs the agent as a node in a graph over the real `FarmState`, so if the
    agent ever writes somewhere other than `crop_recommendation` the result
    disappears here exactly as it would in the orchestrator.
    """
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
    graph.add_node("cropselector", AGENT)
    graph.add_edge(START, "cropselector")
    graph.add_edge("cropselector", END)
    final = await graph.compile().ainvoke({
        "query": "What should I sow?", "lat": 23.02, "lon": 72.57,
        "weather_data": None, "irrigation_advice": None, "crop_recommendation": None,
        "soil_data": {"soil_ph": 8.0, "electrical_conductivity": 0.58,
                      "soil_moisture": 30.0, "soil_type": "black cotton",
                      "air_temperature": 30.0, "air_humidity": 60.0},
    })
    block = final.get("crop_recommendation") or {}
    return (block.get("agent_status") == "success"
            and block["result"]["status"] == "ok"
            and block["result"]["recommendations"])


async def case_orchestrator_state_uses_supplied_weather():
    """Forecast from `weather_data` is used; the Weather API is not called again."""
    weather = {"forecast_long_term": [
        {"date": "2026-06-01", "temp_min": 26.0, "temp_max": 34.0, "humidity": 60.0},
        {"date": "2026-06-02", "temp_min": 27.0, "temp_max": 35.0, "humidity": 64.0},
    ]}
    r = await AGENT.predict({
        "soil_data": {"soil_ph": 7.8, "electrical_conductivity": 0.5,
                      "soil_moisture": 30.0, "soil_type": "Black Cotton"},
        "month": "June", "weather_data": weather, "region": "Gujarat",
    })
    return any("Temperature taken from the 2-day forecast mean (30.5 C)" in w
               for w in r.warnings)


async def case_legacy_crop_selector_payload_is_scored():
    r = await AGENT.predict({
        "farm_id": "farm_123",
        "soil_data": {"ph": 7.8, "ec": 0.5, "moisture": 30.0,
                      "npk": {"n": 280, "p": 45, "k": 210}, "soil_type": "loamy",
                      "humidity": 60.0},
        "location": {"lat": 23.02, "lon": 72.57},
        "season": "kharif", "water_availability": "moderate",
        "farmer_goals": ["high_yield"], "previous_crops": ["wheat"],
        "region": "Gujarat",
    })
    warned = " ".join(r.warnings)
    return (r.status in (PredictionStatus.OK, PredictionStatus.NO_SUITABLE_CROP)
            and "read as 'Loam'" in warned
            and "opening sowing month, June" in warned
            and "has no stated unit" in warned)


async def case_soil_temperature_never_feeds_the_heat_veto():
    """Legacy `temperature` may be soil temperature: it must not act as air."""
    r = await AGENT.predict({
        "soil_data": {"ph": 7.8, "ec": 0.5, "moisture": 30.0,
                      "soil_type": "Black Cotton", "temperature": 58.0},
        "month": "June", "region": "Gujarat",
    })
    return (r.status is PredictionStatus.OK
            and any("temperature was ignored" in w for w in r.warnings))


async def case_unmappable_soil_is_rejected_not_guessed():
    out = await AGENT.run({
        "soil_data": {"soil_ph": 6.5, "electrical_conductivity": 0.4,
                      "soil_moisture": 40.0, "soil_type": "peaty"},
        "month": "June"})
    block = out["crop_recommendation"]
    return block["agent_status"] == "invalid_input" and "soil_type" in block["error"]


async def case_missing_month_defaults_to_current_month_with_a_warning():
    from datetime import date
    from AI_Backend.agents.crop_planning_growth.crop_prediction.inputs import normalize

    payload, notes = normalize({"ph": 7.0, "ec_ds_m": 0.4, "moisture_percent": 25.0,
                                "soil_type": "Loam"}, today=date(2026, 2, 10))
    return payload["month"] == "February" and any("current month" in n for n in notes)


async def case_farm_id_without_readings_is_a_clear_error():
    """The agent never looks readings up itself - the Node backend sends them.
    A request without them must say exactly which ones are missing."""
    out = await AGENT.run({"farm_id": "not-a-uuid"})
    block = out["crop_recommendation"]
    return (block["agent_status"] == "invalid_input" and block["result"] is None
            and "ph" in block["error"] and "soil_type" in block["error"])


async def case_varieties_carry_sowing_window_and_duration():
    r = await predict(ph=8.0, ec_us_cm=580, soil_type="Black Cotton", month="June",
                      forecast_temp_mean_c=30.7, forecast_humidity_mean_percent=55.0,
                      forecast_rain_mm=620)
    return all(v.sowing_window and v.duration_days
               for c in r.recommendations for v in c.top_varieties)


# ---------------------------------------------------------------------------
# the task scheduler gets a block it can validate - and nothing on a refusal
# ---------------------------------------------------------------------------
async def case_scheduler_block_validates_and_rescales():
    from datetime import date

    from AI_Backend.agents.farm_operations_automation.task_scheduler.schemas import (
        CropSelectorAgentData)
    from AI_Backend.agents.farm_operations_automation.task_scheduler.adapters import (
        crop_prediction_output_to_scheduler_block)

    out = await AGENT.run({
        "ph": 8.0, "ec_us_cm": 580, "moisture_percent": 51.2,
        "soil_type": "Black Cotton", "month": "June",
        "forecast_temp_mean_c": 30.7, "forecast_humidity_mean_percent": 55.0,
        "forecast_rain_mm": 620, "region": "Gujarat"})
    block = crop_prediction_output_to_scheduler_block(
        out["crop_recommendation"], today=date(2026, 5, 20))
    data = CropSelectorAgentData.model_validate(block)
    top = out["crop_recommendation"]["result"]["recommendations"][0]
    return (data.recommended_crops[0].crop_name == top["crop"]
            and abs(data.recommended_crops[0].suitability_score
                    - top["suitability_score"] / 10) < 0.01
            and data.planting_window_start is not None
            and data.planting_window_start.year == 2026)


async def case_scheduler_gets_nothing_to_plant_on_a_refusal():
    from AI_Backend.agents.farm_operations_automation.task_scheduler.schemas import (
        CropSelectorAgentData)
    from AI_Backend.agents.farm_operations_automation.task_scheduler.adapters import (
        crop_prediction_output_to_scheduler_block)

    refused = await AGENT.run({
        "ph": 9.6, "ec_ds_m": 8.5, "moisture_percent": 5.0,
        "soil_type": "Saline-Alkaline", "month": "January",
        "forecast_temp_mean_c": 47.0, "forecast_humidity_mean_percent": 12.0,
        "forecast_rain_mm": 5, "region": "Gujarat"})
    failed = await AGENT.run({"ph": 7.0})
    blocks = [crop_prediction_output_to_scheduler_block(x["crop_recommendation"])
              for x in (refused, failed)]
    return all(CropSelectorAgentData.model_validate(b).recommended_crops == []
               for b in blocks)


def case_sowing_window_wraps_the_year():
    from datetime import date

    from AI_Backend.agents.farm_operations_automation.task_scheduler.adapters.crop_prediction_to_scheduler import (
        sowing_window_dates)

    inside = sowing_window_dates("November-January", date(2026, 12, 15))
    upcoming = sowing_window_dates("June-July", date(2026, 9, 22))
    garbage = sowing_window_dates("Anytime", date(2026, 9, 22))
    return (inside == (date(2026, 11, 1), date(2027, 1, 31))
            and upcoming == (date(2027, 6, 1), date(2027, 7, 31))
            and garbage == (None, None))


# ---------------------------------------------------------------------------
# the serving fast path must equal the training-time feature code
# ---------------------------------------------------------------------------
def case_fast_feature_row_matches_add_engineered():
    """`build_feature_row` re-derives the ten engineered columns as scalars.

    If it ever drifts from `features.add_engineered` the classifier is fed
    different numbers than it was trained on and nothing else would notice.
    """
    import itertools

    import pandas as pd

    from AI_Backend.ml.crop_prediction.features import (
        MONTH_NUM, SOIL_ORDER, add_engineered)
    from AI_Backend.ml.crop_prediction.recommend import (
        build_feature_row, _season_for_month)

    for soil, month in itertools.product(SOIL_ORDER, list(MONTH_NUM)[::3]):
        for ph, ec, oc, moist in itertools.product(
                [5.1, 7.5, 8.9], [0.0, 6.0], [0.1, 2.0], [0.0, 51.2]):
            slow = add_engineered(pd.DataFrame([{
                "pH": ph, "EC_dSm": ec, "OC_percent": oc,
                "moisture_percent": moist, "soil_type": soil, "month": month,
                "season": _season_for_month(month)}]))
            fast = build_feature_row(ph, ec, oc, moist, soil, month)
            if sorted(slow.columns) != sorted(fast.columns):
                return False
            for column in slow.columns:
                if slow[column].iloc[0] != fast[column].iloc[0]:
                    return False
    return True


# ---------------------------------------------------------------------------
# region handling - the cache key comes from the caller
# ---------------------------------------------------------------------------
async def case_unknown_region_is_rejected():
    """A region nobody grows in must not be answered with "nothing suits"."""
    try:
        await predict(ph=6.8, ec_ds_m=0.3, region="Atlantis")
        return False
    except UnknownRegionError:
        return True


async def case_region_casing_does_not_split_the_cache():
    a = await predict(ph=6.8, ec_ds_m=0.3, forecast_temp_mean_c=20.0,
                      forecast_humidity_mean_percent=70.0, forecast_rain_mm=250,
                      region="gujarat")
    b = await predict(ph=6.8, ec_ds_m=0.3, forecast_temp_mean_c=20.0,
                      forecast_humidity_mean_percent=70.0, forecast_rain_mm=250,
                      region="GUJARAT")
    return (a.model_info.region == b.model_info.region == "Gujarat"
            and crops(a) == crops(b))


async def case_region_cache_is_bounded_under_junk_input():
    """Unknown regions must not each leave a loaded model behind."""
    before = len(loaded_regions())
    for i in range(50):
        try:
            await predict(ph=6.8, ec_ds_m=0.3, region=f"Nowhere-{i}")
        except UnknownRegionError:
            pass
    return len(loaded_regions()) == before


async def case_every_all_india_spelling_means_unfiltered():
    """The table writes "All-India"; the engine's fallback looks for "all india".

    Either spelling reaching the filter as a literal region would cut the
    variety table down to the one row carrying that string, so all of them
    normalise to "no filter" and none are advertised as a region.
    """
    for spelling in ("All India", "All-India", "india", "ALL"):
        r = await predict(ph=6.8, ec_ds_m=0.3, forecast_temp_mean_c=20.0,
                          forecast_humidity_mean_percent=70.0, forecast_rain_mm=250,
                          region=spelling, top_n=5)
        if r.model_info.region is not None or r.status is not PredictionStatus.OK:
            return False
    return "All-India" not in AGENT.health()["known_regions"]


async def case_all_india_is_treated_as_unfiltered():
    r = await predict(ph=6.8, ec_ds_m=0.3, forecast_temp_mean_c=20.0,
                      forecast_humidity_mean_percent=70.0, forecast_rain_mm=250,
                      region="All India", top_n=5)
    return r.model_info.region is None and r.status is PredictionStatus.OK


# ---------------------------------------------------------------------------
# caching and observability
# ---------------------------------------------------------------------------
async def case_identical_field_is_served_from_cache():
    clear_cache()
    field = dict(ph=7.9, ec_ds_m=0.44, moisture_percent=31.0,
                 soil_type="Black Cotton", month="June",
                 forecast_temp_mean_c=29.5, forecast_humidity_mean_percent=58.0,
                 forecast_rain_mm=610)
    first = await predict(**field)
    second = await predict(**field)
    return (first.cached is False and second.cached is True
            and crops(first) == crops(second)
            and first.recommendations[0].suitability_score ==
                second.recommendations[0].suitability_score)


async def case_cache_ignores_farm_id_but_not_readings():
    clear_cache()
    field = dict(ph=7.9, ec_ds_m=0.44, moisture_percent=31.0,
                 soil_type="Black Cotton", month="June",
                 forecast_temp_mean_c=29.5, forecast_humidity_mean_percent=58.0,
                 forecast_rain_mm=610)
    await predict(farm_id="farm-a", **field)
    same_field = await predict(farm_id="farm-b", **field)
    different_field = await predict(**{**field, "ph": 6.2})
    return same_field.cached is True and different_field.cached is False


async def case_request_id_is_echoed_and_latency_reported():
    r = await predict(ph=8.0, ec_us_cm=580, soil_type="Black Cotton", month="June",
                      forecast_temp_mean_c=30.7, forecast_humidity_mean_percent=55.0,
                      forecast_rain_mm=620, request_id="trace-abc-123")
    return r.request_id == "trace-abc-123" and r.latency_ms is not None \
        and r.processed_at is not None


async def case_health_reports_readiness_and_counters():
    report = AGENT.health()
    return (report["status"] == "ready" and report["model_loaded"] is True
            and "Gujarat" in report["known_regions"]
            and "hit_rate" in report["cache"]
            and report["metrics"].get("holdout_top3") is not None)


# ---------------------------------------------------------------------------
# input leniency - casing yes, guessing no
# ---------------------------------------------------------------------------
def case_soil_type_casing_is_accepted():
    req = CropPredictionRequest(ph=7.0, ec_ds_m=0.5, moisture_percent=25.0,
                                soil_type="black cotton", month="june")
    return req.soil_type.value == "Black Cotton" and req.month.value == "June"


async def case_concurrent_requests_are_consistent():
    """Shared model, shared caches: 40 in flight must agree with one alone."""
    clear_cache()
    field = dict(ph=8.0, ec_us_cm=580, moisture_percent=51.2,
                 soil_type="Black Cotton", month="June",
                 forecast_temp_mean_c=30.7, forecast_humidity_mean_percent=55.0,
                 forecast_rain_mm=620)
    reference = crops(await predict(**field))
    results = await asyncio.gather(*[predict(**field) for _ in range(40)])
    return all(crops(r) == reference for r in results)


def case_contended_scoring_survives_a_second_event_loop():
    """The concurrency guard must not bind itself to one event loop.

    An `asyncio.Semaphore` attaches to the loop that first blocks on it and
    raises on every other one. Under a single server loop that never shows;
    it surfaces in a worker, a script or a test that calls `asyncio.run`
    twice. Each of these runs is its own loop, and each one contends.
    """
    field = dict(ph=7.1, ec_ds_m=0.33, moisture_percent=27.0,
                 soil_type="Loam", month="November",
                 forecast_temp_mean_c=21.0, forecast_humidity_mean_percent=68.0,
                 forecast_rain_mm=300)

    import concurrent.futures

    async def burst(offset):
        results = await asyncio.gather(
            *[predict(**{**field, "ph": 6.5 + (offset * 50 + i) * 0.01})
              for i in range(config_max_concurrency() * 2)])
        return all(r.status is PredictionStatus.OK for r in results)

    def in_own_loop(offset):
        # A fresh thread means a fresh event loop, which is what a worker or
        # a second `asyncio.run` gives you in production.
        return asyncio.run(burst(offset))

    clear_cache()
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        return all(pool.map(in_own_loop, range(3)))


def config_max_concurrency() -> int:
    from AI_Backend.agents.crop_planning_growth.crop_prediction import config
    return config.MAX_CONCURRENT_SCORINGS


# ---------------------------------------------------------------------------
# Agronomy - hand-computed answers
# ---------------------------------------------------------------------------
from AI_Backend.agents.crop_planning_growth.crop_prediction import agronomy  # noqa: E402


def synthetic_climate(mm_per_day_by_year):
    """A Climatology whose every day in year i has the given rain."""
    from datetime import date as _date, timedelta as _td
    days = {}
    for i, mm in enumerate(mm_per_day_by_year):
        d = _date(2015 + i, 1, 1)
        while d.year == 2015 + i:
            days[d] = {"rain": mm, "temp": 28.0, "rh": 70.0}
            d += _td(days=1)
    return climate_mod.Climatology(days, 23.0, 72.5)


def case_crop_demand_follows_the_fao56_kc_curve():
    curve = climate_mod.crop_demand_curve(120)
    return (len(curve) == 120 and abs(sum(curve) - 1.0) < 1e-9
            and curve[0] < curve[60] and curve[-1] < curve[60]      # low, peak, decline
            and abs(curve[0] / curve[60] - 0.4) < 1e-9)             # Kc ini / Kc mid


def case_water_balance_bounds():
    # Rain every day far above demand: the crop never runs short.
    soaked = synthetic_climate([20.0] * 10).rainfed_supply_by_year(6, 120, 500, 200)
    # No rain: only the water stored at sowing (half of 200 mm) can be used,
    # so at most 100 of the 500 mm need is met.
    dry = synthetic_climate([0.0] * 10).rainfed_supply_by_year(6, 120, 500, 200)
    return all(abs(r - 1.0) < 1e-9 for r in soaked) and all(0 < r <= 0.2 + 1e-9 for r in dry)


def case_heavy_soil_stores_monsoon_water():
    """A burst of rain then drought: a deep clay bucket carries the crop further."""
    from datetime import date as _date, timedelta as _td
    days = {}
    for y in range(2015, 2025):
        d = _date(y, 1, 1)
        while d.year == y:
            burst = d.month == 6 and d.day <= 10
            days[d] = {"rain": 40.0 if burst else 0.0, "temp": 28.0, "rh": 70.0}
            d += _td(days=1)
    c = climate_mod.Climatology(days, 23.0, 72.5)
    clay = c.rainfed_supply_by_year(6, 105, 535, 200 * 0.75)[0]   # Black Cotton, groundnut
    sand = c.rainfed_supply_by_year(6, 105, 535, 60 * 0.75)[0]    # Sandy, groundnut
    return clay > sand + 0.1


def case_water_security_categories():
    taw = 150.0
    wet = synthetic_climate([20.0] * 10)                  # every season adequate
    alternating = synthetic_climate([20.0, 0.0] * 5)      # half the seasons fail
    dry = synthetic_climate([0.0] * 10)                   # rain never carries it
    rainfed = agronomy.water_security(wet, 6, 120, 500, taw, None)
    supplemental = agronomy.water_security(alternating, 6, 120, 500, taw, None)
    essential = agronomy.water_security(dry, 6, 120, 500, taw, None)
    no_irrigation = agronomy.water_security(dry, 6, 120, 500, taw, False)
    return (rainfed["category"] == "rainfed" and rainfed["seasons_rain_sufficient"] == 10
            and supplemental["category"] == "supplemental_irrigation"
            and supplemental["seasons_rain_sufficient"] == 5
            and essential["category"] == "irrigation_essential"
            and essential["rain_met_percent_median"] <= 15
            and "heavy losses" in no_irrigation["message"])


def case_drying_soil_slows_uptake():
    """FAO-56 Ks: below the readily-available water the crop draws ever more slowly.

    No rain, 100 mm bucket starting half full, modest 100 mm need. Without the
    stress coefficient the crop would empty all 50 mm stored; with it, uptake
    falls in proportion to what is left and part of the water stays in the soil.
    """
    ratio = synthetic_climate([0.0] * 10).rainfed_supply_by_year(6, 100, 100, 100)[0]
    extracted = ratio * 100
    return 30 < extracted < 48


class _StubClimate:
    """Returns fixed per-season supply ratios, to test classification alone."""

    def __init__(self, ratios):
        self.ratios = ratios

    def rainfed_supply_by_year(self, *_):
        return list(self.ratios)


def case_classification_uses_the_typical_year():
    # Rajkot-cotton pattern: only 3 of 10 seasons adequate, yet a typical season
    # meets 85% of the need - protective irrigation, not "essential".
    near_miss = agronomy.water_security(_StubClimate([1.0] * 3 + [0.85] * 7),
                                        6, 174, 840, 270, None)
    # Rain meets half the need in a typical year: irrigation is essential.
    short = agronomy.water_security(_StubClimate([0.95] * 2 + [0.5] * 8),
                                    6, 174, 840, 270, None)
    return (near_miss["category"] == "supplemental_irrigation"
            and short["category"] == "irrigation_essential")


def case_root_depth_sets_the_bucket():
    # FAO-56 Table 22 midpoints: potato 0.5 m, cotton 1.35 m; Black Cotton 200 mm/m.
    return (agronomy.root_zone_water_mm("Potato", 200) == 100.0
            and agronomy.root_zone_water_mm("Cotton", 200) == 270.0)


def case_soil_nutrients_compared_with_crop_range():
    profile = {"N_min": 280.0, "N_max": 560.0, "P_min": 10.0, "P_max": 25.0,
               "K_min": 108.0, "K_max": 280.0}
    out = {n["nutrient"]: n["status"] for n in agronomy.soil_nutrients(
        profile, {"n_kg_ha": 150.0, "p_kg_ha": 18.0, "k_kg_ha": 400.0})}
    return out == {"N": "low", "P": "adequate", "K": "high"}


def case_rotation_notes():
    solanaceae = agronomy.rotation_notes("Potato", ["Tomato"])
    after_legume = agronomy.rotation_notes("Cotton", ["Groundnut"])
    legume_after_cereal = agronomy.rotation_notes("Guar", ["wheat"])
    same = agronomy.rotation_notes("Cotton", ["cotton"])
    return (any("Solanaceae" in n and "blight" in n for n in solanaceae)
            and any("residual nitrogen" in n for n in after_legume)
            and any("good rotation" in n for n in legume_after_cereal)
            and any("Same crop as last season" in n for n in same)
            and agronomy.rotation_notes("Cotton", ["unknown-crop"]) == [])


def case_mango_flagged_as_perennial_investment():
    advice = agronomy.for_crop("Mango", {"crop_duration_days": 121, "water_req_mm": 945},
                               7, synthetic_climate([5.0] * 10), {}, None, None)
    return advice["perennial"] and advice["water_security"] is None \
        and "20+ year investment" in advice["notes"][0]


# ---------------------------------------------------------------------------
# Climate and agronomy - end to end through the agent
# ---------------------------------------------------------------------------
KHARIF_FIELD = dict(ph=7.8, ec_ds_m=0.5, moisture_percent=30.0, soil_type="Black Cotton",
                    month="June", location={"lat": 23.02, "lon": 72.57}, region="Gujarat")


async def case_season_climate_fills_the_inputs():
    reset_climate()
    r = await AGENT.predict(dict(KHARIF_FIELD))
    # 122 days from 1 June: Jun-Sep all monsoon days in the fake climate.
    return (r.climate is not None and r.climate.years == 10
            and 800 <= r.climate.rain_median_mm <= 850
            and any("climate record" in w for w in r.warnings)
            and not any("water-requirement check was skipped" in w for w in r.warnings)
            and r.climate.temp_mean_c == 29.0)


async def case_caller_values_beat_climate():
    reset_climate()
    r = await AGENT.predict({**KHARIF_FIELD, "forecast_rain_mm": 300.0,
                             "forecast_temp_mean_c": 31.0,
                             "forecast_humidity_mean_percent": 50.0})
    return not any("climate record" in w for w in r.warnings)


async def case_each_crop_gets_water_security():
    reset_climate()
    r = await AGENT.predict(dict(KHARIF_FIELD))
    return all(c.agronomy and c.agronomy.water_security for c in r.recommendations
               if c.crop != "Mango")


async def case_no_irrigation_warns_when_top_crop_needs_it():
    reset_climate(monsoon_mm_per_day=1.0)      # a dry place: ~120 mm a season
    r = await AGENT.predict({**KHARIF_FIELD, "irrigation_available": False,
                             "forecast_temp_mean_c": 30.0,
                             "forecast_humidity_mean_percent": 60.0})
    first = r.recommendations[0]
    return (first.agronomy.water_security.category == "irrigation_essential"
            and any("you reported none" in w for w in r.warnings))


async def case_climate_outage_still_scores():
    reset_climate()
    original = AGENT.service.climate_transport
    AGENT.service.climate_transport = httpx.MockTransport(lambda r: httpx.Response(503))
    try:
        r = await AGENT.predict({**KHARIF_FIELD, "forecast_temp_mean_c": 30.0,
                                 "forecast_humidity_mean_percent": 60.0})
    finally:
        AGENT.service.climate_transport = original
    return (r.status is PredictionStatus.OK and r.climate is None
            and any("Climate history" in w for w in r.warnings))


async def case_sensor_npk_is_not_compared_with_crop_needs():
    """7-in-1 sensor NPK is EC-derived: disclosed, never turned into a nutrient finding."""
    reset_climate()
    r = await AGENT.predict({
        "soil_data": {"soil_ph": 7.8, "electrical_conductivity": 0.5, "soil_moisture": 30.0,
                      "soil_type": "Black Cotton", "nitrogen": 100.0, "phosphorus": 8.0,
                      "potassium": 100.0},
        "month": "June", "region": "Gujarat",
        "forecast_temp_mean_c": 30.0, "forecast_humidity_mean_percent": 60.0,
        "forecast_rain_mm": 700.0})
    return (not r.recommendations[0].agronomy.soil_nutrients
            and any("estimate them from conductivity" in w for w in r.warnings))


async def case_rotation_reaches_the_response():
    reset_climate()
    r = await AGENT.predict({**KHARIF_FIELD, "previous_crops": ["cotton"],
                             "forecast_temp_mean_c": 30.0,
                             "forecast_humidity_mean_percent": 60.0})
    cotton = next((c for c in r.recommendations if c.crop == "Cotton"), None)
    return cotton is not None and any("Same crop" in n for n in cotton.agronomy.rotation)


async def case_agronomy_never_changes_the_ranking():
    """The same field with and without every advisory input ranks identically."""
    reset_climate()
    base = {**KHARIF_FIELD, "forecast_rain_mm": 700.0, "forecast_temp_mean_c": 30.0,
            "forecast_humidity_mean_percent": 60.0}
    plain = await AGENT.predict({k: v for k, v in base.items() if k != "location"})
    advised = await AGENT.predict({**base, "previous_crops": ["Tomato", "wheat"],
                                   "irrigation_available": False,
                                   "n_kg_ha": 100, "p_kg_ha": 5, "k_kg_ha": 500})
    return ([(c.crop, c.suitability_score) for c in plain.recommendations]
            == [(c.crop, c.suitability_score) for c in advised.recommendations])


CASES = [
    case_saline_wasteland_is_refused,
    case_extreme_heat_is_refused,
    case_black_cotton_june_suggests_cotton,
    case_cool_rabi_loam_avoids_kharif_cotton,
    case_every_recommendation_carries_reasons,
    case_gujarat_filter_excludes_cabbage,
    case_gujarat_returns_local_cultivars,
    case_ec_units_agree,
    case_ec_must_be_named_once,
    case_raw_sensor_ec_in_wrong_field_is_rejected,
    case_impossible_ph_is_rejected,
    case_unknown_soil_type_is_rejected,
    case_abbreviated_month_is_rejected,
    case_refusal_keeps_closest_out_of_recommendations,
    case_top_n_is_honoured,
    case_npk_advises_but_never_changes_the_ranking,
    case_problems_surface_failing_checks,
    case_response_is_json_serialisable,
    case_orchestrator_run_reports_invalid_input,
    case_orchestrator_run_returns_dict,
    case_unknown_region_is_rejected,
    case_region_casing_does_not_split_the_cache,
    case_region_cache_is_bounded_under_junk_input,
    case_all_india_is_treated_as_unfiltered,
    case_every_all_india_spelling_means_unfiltered,
    case_identical_field_is_served_from_cache,
    case_cache_ignores_farm_id_but_not_readings,
    case_request_id_is_echoed_and_latency_reported,
    case_health_reports_readiness_and_counters,
    case_soil_type_casing_is_accepted,
    case_concurrent_requests_are_consistent,
    case_fast_feature_row_matches_add_engineered,
    case_contended_scoring_survives_a_second_event_loop,
    case_result_survives_the_langgraph_state,
    case_orchestrator_state_uses_supplied_weather,
    case_legacy_crop_selector_payload_is_scored,
    case_soil_temperature_never_feeds_the_heat_veto,
    case_unmappable_soil_is_rejected_not_guessed,
    case_missing_month_defaults_to_current_month_with_a_warning,
    case_farm_id_without_readings_is_a_clear_error,
    case_varieties_carry_sowing_window_and_duration,
    case_scheduler_block_validates_and_rescales,
    case_scheduler_gets_nothing_to_plant_on_a_refusal,
    case_sowing_window_wraps_the_year,
    case_crop_demand_follows_the_fao56_kc_curve,
    case_water_balance_bounds,
    case_heavy_soil_stores_monsoon_water,
    case_water_security_categories,
    case_root_depth_sets_the_bucket,
    case_drying_soil_slows_uptake,
    case_classification_uses_the_typical_year,
    case_soil_nutrients_compared_with_crop_range,
    case_rotation_notes,
    case_mango_flagged_as_perennial_investment,
    case_season_climate_fills_the_inputs,
    case_caller_values_beat_climate,
    case_each_crop_gets_water_security,
    case_no_irrigation_warns_when_top_crop_needs_it,
    case_climate_outage_still_scores,
    case_sensor_npk_is_not_compared_with_crop_needs,
    case_rotation_reaches_the_response,
    case_agronomy_never_changes_the_ranking,
]


async def main() -> bool:
    passed = 0
    for case in CASES:
        name = case.__name__.removeprefix("case_").replace("_", " ")
        try:
            result = case()
            ok = bool(await result) if asyncio.iscoroutine(result) else bool(result)
        except Exception as exc:  # noqa: BLE001
            ok = False
            name = f"{name}  ({type(exc).__name__}: {exc})"
        passed += ok
        print(f"[{'PASS' if ok else 'FAIL'}] {name}")
    print(f"\n{passed}/{len(CASES)} checks passed")
    return passed == len(CASES)


if __name__ == "__main__":
    sys.exit(0 if asyncio.run(main()) else 1)
