# Crop Prediction Agent

**The one crop agent in FarmXpert.** Ranks the crops worth considering on a
field from soil sensor readings, a weather forecast and a sowing month. Wraps the validated FarmXpert
recommender (`AI_Backend/ml/crop_prediction/`) — 6,771 rows, 10 crops,
344 varieties, deployed for **Gujarat** (9 crops, 66 varieties).

```
POST /crop-prediction/predict   -> ranked crops + varieties + reasons
GET  /crop-prediction/health    -> readiness, metrics, live cache counters
GET  /crop-prediction/regions   -> regions the variety table covers
```

## Running the API

The router is mounted in `AI_Backend/main.py` with every other agent, which
is how it ships. `main.py` needs `DATABASE_URL` set, because other routers
import a database session at import time. Crop prediction needs no database,
so it also has a standalone entry point for deployment, load testing and
debugging without the rest of the backend:

```bash
python -m uvicorn main:app --app-dir AI_Backend --port 8000   # mounts /crop-prediction
```

Interactive docs at `http://127.0.0.1:8100/docs`. A request:

```bash
curl -X POST http://127.0.0.1:8100/crop-prediction/predict -H "Content-Type: application/json" -d "{\"farm_id\":\"farm-sunrise-001\",\"ph\":8.0,\"ec_us_cm\":580,\"moisture_percent\":51.2,\"soil_type\":\"Black Cotton\",\"month\":\"June\",\"forecast_temp_mean_c\":30.7,\"forecast_humidity_mean_percent\":55.0,\"forecast_rain_mm\":620,\"region\":\"Gujarat\",\"top_n\":3}"
```

Inside the full backend the same call goes to
`http://127.0.0.1:8000/crop-prediction/predict`.

| Status | When |
|---|---|
| 200 | Scored — **including `status: "no_suitable_crop"`**, which is an answer |
| 422 | Bad reading, EC without a named unit, or an unknown region |
| 503 | Model artifacts unavailable (also `GET /health` while still loading) |
| 504 | Scoring exceeded `CROP_PREDICTION_TIMEOUT` |

Omit `region`, or send "All India" in any spelling, to score every variety.

## Why there is only one crop agent

This replaced the earlier `crop_selector`, which was removed. That agent ran
a generic 22-crop model (coffee, coconut, jute, apple...) on soil NPK and one
day's rainfall, then let an LLM re-rank the list and invent yields and
profits. It also loaded its XGBoost model at import time, so without
`xgboost` installed it took `main.py` and the orchestrator down with it.

What it did well was carried over:

| Old crop_selector | Here |
|---|---|
| Nested `soil_data` payload | `inputs.py` accepts it, plus orchestrator state |
| `farm_id` → stored readings | `repository.py` — the old import path never existed, so it silently always failed |
| Orchestrator node `cropselector` | Same node, same `crop_recommendation` state key |
| Feeds the task scheduler | `orchestrator/adapters/crop_prediction_to_scheduler.py` |
| LLM ranking | Dropped. Optional narration only — it cannot re-rank |

## What callers can send

`POST /crop-prediction/predict` takes the strict native request. The agent
itself (`predict()` / `run()`) also accepts:

- **Legacy nested shape** — readings under `soil_data` (`ph`, `ec`,
  `moisture`, `npk`, `soil_type`), `season`, `location`.
- **Orchestrator state** — `lat`/`lon`, raw readings under `soil_data` in
  the Soil Health vocabulary (`soil_ph`, `electrical_conductivity`,
  `air_temperature`...), and Weather Watcher output under `weather_data`,
  which is used instead of calling the weather API again.
- **Only a `farm_id`** — the farm's latest stored readings are used. Needs
  the database; without it the call fails with a clear message, never
  with an empty reading.

Every inference is reported in `warnings`: a season scored as its opening
sowing month (Kharif → June, Rabi → October, Zaid → March), no month at all
scored as the current month, "loamy" read as "Loam". What cannot be mapped
without guessing is rejected — "peaty" has no equivalent among the ten
soil classes — and a legacy `temperature` reading is ignored, because it may
be soil temperature and would otherwise drive the air-temperature veto.

## In the orchestrator

`run(state)` returns exactly `{"crop_recommendation": {...}}` — the key
`FarmState` declares. **LangGraph silently drops any other key a node
returns**, so writing anywhere else would lose the result with no error.

```python
{"crop_recommendation": {"agent_status": "success", "result": {...response...}}}
{"crop_recommendation": {"agent_status": "invalid_input", "result": None, "error": "..."}}
```

`agent_status` is one of success, invalid_input, timeout, error. Pass the
block to `crop_prediction_output_to_scheduler_block()` for the task
scheduler: suitability is rescaled to the scheduler's 0–10, the planting
window comes from the top variety's sowing window, and on `no_suitable_crop`
or any failure `recommended_crops` is **empty**, so the scheduler never
plans planting on a field the model refused.

## Layout

Tests live in `AI_Backend/tests/` (`test_crop_prediction.py`, 62 checks).

| File | Purpose |
|---|---|
| `schemas.py` | Request/response contract; unit and range validation at the boundary |
| `model_loader.py` | Shared artifacts, region normalisation, readiness |
| `cache.py` | Bounded TTL cache for scored fields |
| `service.py` | Maps engine output to the contract; caching, limits, enrichment |
| `agent.py` | `BaseAgent` implementation — `run()` for the orchestrator, `predict()` direct |
| `inputs.py` | Adapts legacy / orchestrator payloads to the native request |
| `repository.py` | Latest stored soil readings for a `farm_id` |
| `config.py` | Serving knobs. Model thresholds stay in the engine |
| `climate.py` | ERA5 season climatology + FAO-56 daily soil water balance |
| `agronomy.py` | Per-crop water security, soil nutrients, rotation, perennials |

The engine is vendored under `AI_Backend/ml/crop_prediction/` with artifacts
in `AI_Backend/ml/models/crop_prediction/`. **The scoring arithmetic is
untouched** — only loading, caching and per-request data shapes changed, and
every field scores identically to the model repo (verified by diffing full
outputs across thousands of fields; the repo's own suite still reports 9/9).

## The five rules for callers

1. **Branch on `status` first.** `no_suitable_crop` is a real answer: say so.
   `closest` is diagnostic and must never be shown as a recommendation — the
   classifier was trained only on crops that succeeded, so it cannot refuse,
   and the rule layer's veto is the only thing here that can.
2. **Show three crops, not one.** Top-1 is 80.6%, top-3 is 99.0%.
3. **Narrate `reasons`.** The reason list, not the crop name, is the output
   worth having; `problems` is the subset the farmer can act on.
4. **Never re-rank with LLM reasoning.** Narration is retelling, never ranking.
5. **Never present this as agronomic advice.** Carry `disclaimer` through.

## Agronomy — what comes with each recommended crop

The shortlist order belongs to the validated model and nothing below changes
it (a test asserts identical rankings with and without every advisory input).
Each recommendation carries `agronomy`; the response carries `climate`.

**Season climate.** With a `location`, the missing season inputs (rain,
temperature and humidity over the 120 days from sowing) come from ten years of
ERA5 reanalysis at that spot, cached for 30 days. This replaces a 14-day
forecast mean standing in for a four-month season, and means the water check
is no longer skipped. The caller's own values always take precedence.

**Water security.** For every one of the last ten seasons, a daily FAO-56 soil
water balance is run over the crop's own duration:
- the root-zone "bucket" is the soil's available water × the crop's rooting
  depth (FAO-56 Table 22);
- demand follows the FAO-56 Kc curve;
- uptake slows as the soil dries (the FAO-56 Ks coefficient).

A season counts as adequate when rain meets ≥ 90 % of the need (about ≤ 10 %
yield loss). The crop is classed **rainfed** when ≥ 8 of 10 seasons are
adequate, **irrigation_essential** when even a typical season falls below
70 %, and **supplemental_irrigation** otherwise.

It was checked against Gujarat practice across Surat, Ahmedabad, Rajkot and
Bhuj for groundnut, cotton, guar, potato and ajwain, and agreed in every case.
An earlier version, based on USDA-SCS effective rainfall, called kharif
groundnut in Ahmedabad "irrigation essential in 10/10 years". That was wrong,
because it ignored the monsoon water that heavy soils store, so it was
replaced.

**Soil nutrients.** The dataset's N/P/K columns are the *soil available-
nutrient range each crop does well in* on the Indian soil-test scale (kg/ha).
They are not fertiliser doses, whatever the model repo assumed. Groundnut is
listed at N 294–588 / P 10.5–25.7 / K 102.6–273.9, which is the "medium"
fertility class, and 65 rows have K_min exactly on the 108 kg/ha class
boundary. So `n_kg_ha` / `p_kg_ha` / `k_kg_ha` from a soil test are compared
with each crop's range (low / adequate / high). Soil-Health-style mg/kg values
are converted (× 2.025, 0–15 cm, bulk density 1.35).

**Rotation.** `previous_crops` triggers notes on same-crop and same-family
carry-over (for example Solanaceae blight and wilt), the nitrogen credit after
a legume, and legume-after-cereal benefits.

**Perennials.** Mango is flagged as a 20+ year orchard investment and not a
seasonal choice.

## Units — the likely integration bug

EC must be named: send `ec_us_cm: 580` or `ec_ds_m: 0.58`, never both and
never neither. `580` in the dS/m field is rejected rather than scored — as a
salt pan it would veto every variety and tell the farmer nothing grows here.
pH outside 3–10 is rejected as a sensor fault; outside 5.1–9.0 it is scored
with a warning. NaN and infinity are rejected on every numeric field.
`forecast_rain_mm` is the **total over the growing window**.

Casing and stray whitespace are forgiven on `soil_type` and `month`
("black cotton" works). Abbreviations are not: "Nov" is a different value,
not a different spelling, and guessing is how a field gets scored for the
wrong season.

Soil NPK (`n_kg_ha` and friends) is not part of the suitability score, because the
validated model does not take it. It *is* compared with each crop's soil
nutrient range; see Agronomy above.

## Regions

`region` is validated against the states named in the variety table and
normalised to the table's spelling, so "gujarat" and "GUJARAT" share one
cache entry. An unknown region is a **422, not an empty shortlist**: filtering
to nothing would otherwise report "no crop is suitable" for a field that may
be perfectly plantable. "All India" means unfiltered.

## Performance

Measured on this machine, Gujarat, warm process:

| Path | p50 | p95 |
|---|---|---|
| Unique field (full scoring) | 15 ms | 18 ms |
| Repeat field (cache hit) | 0.9 ms | 1.2 ms |
| 60 concurrent unique fields | 8.4 ms/req | — |

Startup loads the artifacts once (~2 s) via the app's `lifespan` hook, so no
request pays for it. What the work went into:

- **One copy of the model per process.** Building a `Recommender` used to
  re-read the 3.4 MB joblib bundle for every region.
- **No `iterrows` in the request path.** The variety table is converted to
  plain dicts once at load, and each variety's sowing window is parsed once
  instead of per request: the sweep went 5.5 ms → 2.1 ms for Gujarat and
  34 ms → 11 ms for all-India.
- **A single-row feature builder.** `features.add_engineered` inserts ten
  derived columns one at a time, which is right for training and wasteful for
  one row; `build_feature_row` evaluates the same ten formulas as scalars.
  A regression check compares the two column by column.
- **Deterministic results are cached** (512 entries, 15-minute TTL) keyed on
  the readings only — `farm_id` is not part of the key, because two farms
  with the same readings are the same field to the scorer.

Not done on purpose: `sklearn.set_config(assume_finite=True)` would shave
~1.5 ms off inference, but it is process-global and would change how every
other model in this backend validates its input. Not worth it for one agent.

## Configuration

| Env var | Default | Meaning |
|---|---|---|
| `CROP_PREDICTION_REGION` | `Gujarat` | Deployed region filter |
| `CROP_PREDICTION_WARMUP_REGIONS` | `Gujarat` | Comma-separated, loaded at startup |
| `CROP_PREDICTION_TOP_N` | `3` | Default shortlist length |
| `CROP_PREDICTION_CACHE` | `true` | Scoring cache on/off |
| `CROP_PREDICTION_CACHE_SIZE` | `512` | Max cached fields |
| `CROP_PREDICTION_CACHE_TTL` | `900` | Seconds before an entry is re-scored |
| `CROP_PREDICTION_MAX_CONCURRENCY` | `8` | Concurrent scorings |
| `CROP_PREDICTION_TIMEOUT` | `15` | Seconds before a scoring is abandoned (504) |
| `CROP_PREDICTION_SLOW_MS` | `250` | Log threshold for a slow request |
| `CROP_PREDICTION_WEATHER` | `true` | Weather Watcher enrichment |
| `CROP_PREDICTION_LLM` | `false` | LLM narration (needs `Groq_API`) |

## Operating it

Every response carries `request_id` (echoed from the request or generated),
`cached` and `latency_ms`; the route also sets `X-Request-ID` and `X-Cache`
headers. Requests slower than `CROP_PREDICTION_SLOW_MS` log at WARNING with
the id, so a regression is visible without a profiler. `GET /health` returns
503 until the model is loaded — wire it to the readiness probe, not liveness.

## Weather enrichment

When `location` is given and the forecast means are missing, the Weather
Watcher agent fills `forecast_temp_mean_c` and `forecast_humidity_mean_percent`
from its 14-day forecast, and each borrowed value is disclosed in `warnings`.
Rainfall is deliberately never borrowed: the engine wants a season total, and
a 14-day total would understate it by an order of magnitude while looking
entirely reasonable. Failures and timeouts degrade to scoring without a
forecast.

## Before and after any change

```bash
python -m AI_Backend.tests.test_crop_prediction
```

Must report 62/62. If a change improves a metric but breaks a check here, the
change is wrong.

After touching anything under `AI_Backend/ml/crop_prediction/`, also run the
equivalence check, which diffs this engine against the model repo over 8,640
fields in three regions (currently 8,640/8,640 identical):

```bash
python -m AI_Backend.tests.verify_crop_engine_equivalence
```
 Known limitation: Tomato is the weak class (F1 0.51),
confused with Coriander — one more reason to show three crops.
