# FarmXpert Orchestration Layer — Architecture

Why this exists, what it does, and what it deliberately does not do.

The orchestrator **coordinates** agents. It never contains farming logic. Every
agronomic decision stays inside the agent that owns it, and the orchestrator
is responsible only for: selection, ordering, concurrency, resilience,
validation, conflict surfacing, provenance and observability.

---

## 1. What the repository actually looked like

Recorded because the design follows from it.

| Agent | Entry point | Needs | Produces | External |
|---|---|---|---|---|
| Weather Watcher | `WeatherAgent().run({lat,lon})` | location | `weather_data` | Open-Meteo / OpenWeather |
| Soil Health | `SoilHealthAgent().run(readings)` | soil pH + EC | `soil_data` | — |
| Irrigation Planner | `IrrigationAgent().run(payload)` | location, crop, stage | `irrigation_advice` | weather (internally) |
| Crop Prediction | `CropPredictionAgent().predict(...)` | pH, EC, month, region | `crop_recommendation` | ERA5, LightGBM |
| Task Scheduler | `TaskSchedulerAgent().run(payload)` | other agents' outputs | `task_plan` | — |
| Market Intelligence | `run_market_agent(MarketQueryInput)` | commodity | `market_insights` | data.gov.in mandi API |

Findings that shaped the design:

1. **Every agent is an in-process async Python callable.** None of them need an
   HTTP hop. Calling our own FastAPI routes over localhost would add latency,
   a second failure mode and a serialization round trip for nothing.
2. **No agent writes to the database.** Only Crop Prediction reads it, opening
   its own short-lived session. So the orchestrator needs no shared session and
   introduces no transaction conflicts.
3. **The previous orchestrator was a prototype** — a LangGraph with four
   hardcoded nodes, a `FarmState` TypedDict that silently drops undeclared
   keys, no timeouts, no retries, no failure policy, and a router that returned
   `str(e)` to the client. Task Scheduler and Market were not wired in at all.
4. **Market Intelligence was broken on import** (`from agents.…` instead of
   `from AI_Backend.agents.…`). Fixed with an absolute import; no behaviour
   change. This is the only edit made to an existing agent.
5. **There was no RAG.** `agents/retrieval_agent/` and
   `Backend/app/infrastructure/vector_store/` were one-line stubs and pgvector
   was commented out in `models/farms.py`.

---

## 2. Layering

```
  routers/orchestrator.py        thin: validate, correlate, translate errors
        │
  orchestration/service.py       one call; owns nothing but the sequence
        │
  planner.py                     intent -> capabilities -> agents -> DAG levels
        │
  engine.py                      concurrency, timeouts, retries, cancellation
        │
  registry.py                    the catalog; the only place agents are named
        │
  orchestration/agents/*.py      adapters: existing agents, unmodified
```

The engine never mentions an agent by name. Adding an agent touches one new
adapter file and one `register()` call — nothing in planner, engine, failure
handling, aggregation or logging.

---

## 3. The agent contract

An adapter declares metadata and one `execute(context)` coroutine
(`contracts.py`):

```python
AgentSpec(
    name="irrigation_planner",
    version="3.0.0",
    capabilities={Capability.IRRIGATION_ADVICE},
    requires_context={"location", "crop"},      # from the request
    depends_on={"weather_watcher"},             # from other agents
    optional_depends_on={"soil_health"},        # used if present, not required
    criticality=Criticality.OPTIONAL,
    timeout_s=12.0,
    retry=RetryPolicy(max_attempts=2, base_delay_s=0.4),
    concurrency_safe=True,
    execute=...,
    validate_output=...,
)
```

`requires_context` vs `depends_on` is the distinction that makes selection
deterministic: the first is data the *caller* must supply, the second is data
another *agent* produces. Both are checked before anything runs.

---

## 4. Agent selection — deterministic, never LLM-decided

1. The caller sends an intent (`daily_plan`, `irrigation`, `crop_choice`,
   `market`, `soil`, `weather`, `ask`) or an explicit agent list.
2. An intent maps to **capabilities**, capabilities map to **registered
   agents**. The map lives in the registry, not in the engine.
3. Dependencies are pulled in transitively (asking for irrigation pulls in
   weather).
4. Agents whose `requires_context` cannot be satisfied are **skipped with a
   reason**, not failed.

An LLM may classify a free-text farmer question into one of the intents above.
It can never name an agent: whatever it returns is intersected with the
registry, and anything unknown is dropped and logged. There is no path from
model output to arbitrary execution.

---

## 5. Execution

* The DAG is validated at **registration time**: unknown dependency or cycle
  raises immediately, so a bad graph can never reach production traffic.
* Kahn's algorithm produces **levels**; every agent in a level runs
  concurrently under a bounded semaphore (`max_concurrency`, default 8).
  An agent marked `concurrency_safe=False` runs alone in its level.
* Each attempt is wrapped in `asyncio.wait_for`, so a timeout **cancels** the
  coroutine rather than leaking it.
* **One deadline governs the whole request** (`FARMXPERT_ORCHESTRATION_DEADLINE_S`,
  default 30 s). Per-agent timeouts alone are not enough: summed across this
  catalog with retries the worst case was about 80 seconds, which no farmer
  waits for. Every per-attempt timeout is clamped to the time remaining, no
  retry starts past the deadline, and anything still pending is returned as
  `timeout` with an explanation rather than silently missing.
* A level runs under `gather(return_exceptions=True)`, so one agent's failure
  never abandons its siblings mid-flight. Cancellation is re-raised rather
  than dressed up as a result: if the caller disconnected, the work stops.
* Failures are classified into `ErrorCode` (`TIMEOUT`, `EXTERNAL_SERVICE`,
  `INVALID_INPUT`, `INVALID_OUTPUT`, `DEPENDENCY_FAILED`, `RATE_LIMITED`,
  `INTERNAL`, …). Only codes marked retryable are retried, bounded, with
  exponential backoff **plus jitter** to avoid retry storms.
* `INVALID_INPUT` and `INVALID_OUTPUT` are never retried: they are
  deterministic and would fail identically.

### Failure policy

| Criticality | Its failure means |
|---|---|
| `REQUIRED` | The orchestration cannot produce a safe answer → `failed`. |
| `OPTIONAL` | Dependents are skipped as `SKIPPED_DEPENDENCY_FAILED`; independent branches continue → `partial_success`. |
| `BEST_EFFORT` | Recorded as a warning; nothing downstream is blocked. |

A dependent of a failed agent is marked **skipped with the root cause named**,
never "failed" — the difference is what an on-call engineer needs at 2 am.
An agent that depends on the failed one only through `optional_depends_on`
still runs, without that input.

**Nothing is ever fabricated.** A missing agent output is absent from the
response, and the reason is in `skipped` or `failed`.

---

## 6. Output validation

An agent's return value is never trusted. Each adapter's `validate_output`
normalizes into `NormalizedOutput(data, confidence, produced_at, freshness,
sources)`. If a result is malformed, missing fields, or impossible
(a percentage above 100, a negative depth), it is marked `INVALID_OUTPUT` and
**not passed downstream**. Downstream agents see only validated data.

Freshness is carried where the agent reports it (a cached forecast knows its
own age). It is never invented: unknown freshness stays `None`.

---

## 7. Conflicts

Agents can disagree — irrigation says "water today", weather says 40 mm of rain
is coming. Conflicts are detected by small, explicit rule functions in
`conflicts.py`, each returning a `Conflict` with the competing claims.

Resolution order is fixed and deliberate:

1. **Safety first** — the option that cannot hurt the crop, the person or the
   consumer wins (a pre-harvest interval always beats a yield argument).
2. **Domain authority** — the agent that owns the decision wins in its own
   domain (irrigation depth belongs to the irrigation agent).
3. **Measurement over model** — observed data beats a forecast; a forecast
   beats an extrapolation.
4. **Freshness** — newer data wins when authority is equal.
5. **Otherwise: surface it.** An unresolved conflict is returned as a conflict,
   with both positions. The orchestrator never invents certainty.

---

## 8. Response contract

`OrchestrationResponse` (see `schemas.py`) carries `request_id`, `status`
(`success` | `partial_success` | `failed` | `validation_error`), a `summary`,
`agent_results` (per-agent status, duration, attempts, confidence, freshness,
error code), `failed`, `skipped` (with root cause), `conflicts`, `warnings`,
`provenance` (which agents contributed to each recommendation) and
`execution` metadata.

Stack traces and exception strings never reach the client. They are logged
with the `request_id` and replaced by an error code plus a safe message.

---

## 9. Observability

One `request_id` per orchestration, on every log line, plus an `execution_id`
per agent attempt. Events are emitted as structured records:
`ORCHESTRATION_STARTED`, `AGENT_SELECTED`, `AGENT_STARTED`, `AGENT_RETRY`,
`AGENT_COMPLETED`, `AGENT_FAILED`, `AGENT_TIMEOUT`, `AGENT_SKIPPED`,
`DEPENDENCY_FAILED`, `AGENT_OUTPUT_INVALID`, `AGENT_CONFLICT_DETECTED`,
`ORCHESTRATION_COMPLETED` / `_PARTIAL_SUCCESS` / `_FAILED`.

Payloads are never logged whole. Only shapes, sizes and codes — no farmer
personal data, no coordinates beyond the rounded cell, no keys or tokens.

---

## 10. LangGraph, LLM, RAG, TOON, MCP

**LangGraph** stays where it belongs. Deterministic coordination — ordering,
timeouts, retries, failure policy — is plain Python here, because that is what
must be provably correct and testable without a model. The existing
`/orchestrator/run` graph endpoint keeps working unchanged. LangGraph remains
available for LLM reasoning flows; the two are not mixed.

**LLM (NVIDIA API)** is used at exactly two edges, never in the middle:
understanding a free-text question into a constrained intent, and turning
validated agent output into the farmer's language. Numbers are passed through,
never recomputed. Configured by `NVIDIA_API_KEY` / `NVIDIA_BASE_URL` /
`NVIDIA_MODEL`; if the key is absent the orchestrator degrades to structured
output instead of failing.

**RAG is an agent, not a special case, and it lives with the other agents.**
`AI_Backend/agents/retrieval_agent/` is a first-class agent with the same
layout as the rest (config, schemas, tools, service, agent, prompts); the
orchestration layer holds only an adapter for it. That boundary matters:
retrieval is a domain capability, so it can be called directly, from a
LangGraph node, or over MCP without going through the orchestrator.

It is *agentic* within a hard ceiling:

1. read the curated map and address the matching documents;
2. stop if that was enough - most questions end here, at no embedding cost;
3. otherwise search the pgvector index;
4. grade the result, and if the best match is weak, rewrite the query **once**
   and keep whichever attempt scored better;
5. return passages and a readable record of what it did.

Step 4 happens at most once. An agent that keeps rewriting answers slightly
better for unbounded cost, and on a farmer-facing path the extra seconds cost
more than the extra relevance is worth.

**The curated layer is scored, not embedded.** Selection weights title, tags
and section headings above the summary, with the document body at low weight
so a farmer describing a symptom ("my wheat is turning yellow") still finds
the right page. A small agronomy synonym map bridges the farmer's word and the
handbook's - "salty" to "salinity", "spray" to "pesticide". Below a minimum
score nothing is returned: answering confidently from the least-bad page is
the classic RAG failure, and an honest "not covered" is the better answer.

**The bundle is generated, not hand-written.** `AI_Backend/knowledge/build_okf.py`
renders 26 documents (19 crops, 7 practices) by READING the agents' own
configuration for every number - pH range, salt tolerance, root depth,
critical stages - and wrapping curated prose around it. Writing those numbers
a second time in Markdown would guarantee the handbook and the agents disagree
within a season. `test_published_facts_match_the_agent_configuration` fails if
the bundle goes stale.

**Prompt cost: what was measured, and what it changed.** Token counts below
are real, from `tiktoken` over the output of an actual five-agent run
(Rajkot, groundnut at flowering):

| Strategy | Tokens | vs naive |
|---|---|---|
| Full payload, pretty JSON | 25,950 | - |
| Full payload, minified JSON | 19,772 | -24% |
| Full payload, TOON | 18,603 | -28% |
| **Projected view, minified JSON** | **2,844** | **-89%** |
| Projected view, TOON | 3,008 | -88% |

Two conclusions, both the opposite of the obvious guess:

1. **Selection beats encoding, by an order of magnitude.** Agent payloads
   carry diagnostics, model versions, duplicated day plans and intermediate
   values that no farmer answer depends on. `prompt_view.project()` selects
   the facts that matter and drops the rest: an 89% cut, against 6% for
   changing syntax. Projection only ever SELECTS - it never rounds, rewrites
   or summarises, because the model is told to copy numbers exactly and must
   never be handed an altered one.
2. **On the projected view, JSON usually wins.** TOON amortises one column
   header over many identical rows; once the view is projected there is
   little repetition left to amortise, and TOON's indentation costs more than
   JSON's punctuation saves. TOON still wins clearly on genuinely tabular
   payloads - a 14-day forecast is 48% cheaper in TOON.

So `llm.build_facts()` projects first, then builds both encodings and sends
the shorter one, naming the format in the system prompt. That is never worse
than committing to either, and it re-measures per payload instead of trusting
a benchmark from one shape of data.

**A warning worth recording.** The first TOON encoder looked like a 63% win.
It was not: its table mode emitted only the scalar columns of a row and
silently dropped every nested field - all 252 do/do-not advice lines on a task
plan, and every reason code on an irrigation schedule. A fidelity check over
1,769 leaf values found it. Tabular form is now used only when every row has
identical keys AND every value is scalar, and `test_toon_never_drops_a_value`
holds that line. A cheaper prompt that loses "do not spray within the
pre-harvest interval" is not a cheaper prompt; it is a wrong answer.

**MCP** is generated from the registry. Every registered agent becomes an MCP
tool automatically, with its schema and description — so a new agent appears in
MCP without touching the MCP server. It exposes the same in-process calls, so
there is no second implementation to keep in sync.

**PostGIS** resolves `farm_id` to a location. `geoalchemy2` is already a
dependency and `farms.py` has the Geography column ready; the orchestrator
reads through a repository function and never builds SQL inline.

---

## 11. Adding an agent later

1. Write the agent (or keep the one you have).
2. Add `orchestration/agents/<name>.py`: a `build()` returning an `AgentSpec`
   with its metadata, an `execute` that calls the existing agent, and a
   `validate_output`.
3. Add one line to `orchestration/agents/__init__.py`.

No change to the engine, planner, registry, failure handling, aggregation,
logging, MCP server or tests. `test_orchestrator.py` proves this with a mock
future agent that is registered and executed without touching engine code.

---

## 12. Deliberate non-goals

* No Celery / Redis / Kafka. Every agent completes in milliseconds to a couple
  of seconds; a synchronous request is the right shape. The service boundary is
  async-ready, so background execution can be added later without touching
  agents.
* No rewrite of working agents. Adapters only.
* No LLM in the safety path.
* No internal HTTP calls to our own endpoints.
