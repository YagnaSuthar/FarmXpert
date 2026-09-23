"""
Orchestration layer — test suite
=================================
Plain runner, no pytest:   python -m AI_Backend.tests.test_orchestrator

Tests behaviour, not implementation. Every agent here is a mock: no network,
no database, no model. What is being verified is the orchestration contract -
ordering, concurrency, failure policy, retries, timeouts, validation,
conflicts, provenance and extensibility.
"""

from __future__ import annotations

import asyncio
import logging
import random
import sys
import time
import traceback
from typing import Any, Dict, List, Optional

from AI_Backend.orchestration.aggregate import (
    overall_confidence,
    overall_status,
    provenance,
    summarise,
    to_skipped,
)
from AI_Backend.orchestration.contracts import (
    AgentSpec,
    AgentStatus,
    Capability,
    Criticality,
    ErrorCode,
    ExecutionContext,
    NormalizedOutput,
    OrchestrationStatus,
    RetryPolicy,
)
from AI_Backend.orchestration.engine import (
    AgentInputError,
    AgentOutputError,
    ExecutionEngine,
    ExternalServiceError,
)
from AI_Backend.orchestration.planner import Intent, Planner
from AI_Backend.orchestration.registry import AgentRegistry, RegistryError
from AI_Backend.orchestration.toon import encode, estimate_tokens

logging.disable(logging.CRITICAL)

PASSED: List[str] = []
FAILED: List[str] = []


def check(name: str, condition: Any, detail: Any = "") -> None:
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


# ── mock agents ─────────────────────────────────────────────────────────────

def passthrough(raw: Any) -> NormalizedOutput:
    return NormalizedOutput(data=raw, confidence=0.9)


def mock(name: str, *, produces: Any = None, capability=Capability.WEATHER_FORECAST,
         depends_on=(), optional_depends_on=(), requires_context=(),
         criticality=Criticality.OPTIONAL, timeout_s=5.0, retry=None,
         delay: float = 0.0, fails: Optional[Exception] = None,
         fail_times: int = 0, validate=passthrough,
         concurrency_safe: bool = True, record: Optional[List] = None) -> AgentSpec:
    """A configurable stand-in for a real agent."""
    state = {"calls": 0}

    async def execute(context: ExecutionContext) -> Any:
        state["calls"] += 1
        if record is not None:
            record.append((name, "start", time.perf_counter()))
        if delay:
            await asyncio.sleep(delay)
        if fails is not None and (fail_times == 0 or state["calls"] <= fail_times):
            raise fails
        if record is not None:
            record.append((name, "end", time.perf_counter()))
        return produces if produces is not None else {"agent": name, "ok": True}

    spec = AgentSpec(
        name=name, version="1.0.0", description=f"mock {name}",
        capabilities=frozenset({capability}),
        execute=execute, validate_output=validate,
        requires_context=frozenset(requires_context),
        depends_on=frozenset(depends_on),
        optional_depends_on=frozenset(optional_depends_on),
        criticality=criticality, timeout_s=timeout_s,
        retry=retry or RetryPolicy(max_attempts=1),
        concurrency_safe=concurrency_safe)
    spec.__dict__["_state"] = state  # frozen dataclass; for assertions only
    return spec


def context(**kwargs) -> ExecutionContext:
    base = dict(request_id="test-request", location={"lat": 22.3, "lon": 70.8})
    base.update(kwargs)
    return ExecutionContext(**base)


def run(engine, plan, ctx):
    return asyncio.run(engine.run(plan, ctx))


def plan_for(registry: AgentRegistry, ctx: ExecutionContext, **kwargs):
    return Planner(registry).plan(ctx, **kwargs)


def fresh(*specs) -> AgentRegistry:
    registry = AgentRegistry()
    for spec in specs:
        registry.register(spec)
    return registry


# ── 1. Happy path ───────────────────────────────────────────────────────────

@case
def test_all_agents_succeed():
    registry = fresh(mock("weather"),
                     mock("soil", capability=Capability.SOIL_ASSESSMENT),
                     mock("irrigation", capability=Capability.IRRIGATION_ADVICE,
                          depends_on={"weather"}))
    ctx = context()
    plan = plan_for(registry, ctx, capabilities=[Capability.IRRIGATION_ADVICE])
    results = run(ExecutionEngine(), plan, ctx)

    check("every selected agent succeeds", all(r.ok for r in results.values()), results)
    check("dependencies are pulled in automatically", "weather" in results)
    specs = {s.name: s for level in plan.levels for s in level}
    check("status is success", overall_status(results, specs) == OrchestrationStatus.SUCCESS)


# ── 2. Ordering and concurrency ─────────────────────────────────────────────

@case
def test_dependencies_run_in_order():
    registry = fresh(mock("weather"),
                     mock("irrigation", capability=Capability.IRRIGATION_ADVICE,
                          depends_on={"weather"}),
                     mock("plan_agent", capability=Capability.WORK_PLAN,
                          depends_on={"irrigation"}))
    ctx = context()
    plan = plan_for(registry, ctx, capabilities=[Capability.WORK_PLAN])
    levels = plan.describe()
    check("three dependency levels", len(levels) == 3, levels)
    check("weather runs first", levels[0] == ["weather"], levels)
    check("plan runs last", levels[-1] == ["plan_agent"], levels)


@case
def test_independent_agents_run_concurrently():
    """Three 200 ms agents must finish in well under 600 ms."""
    timeline: List = []
    registry = fresh(
        mock("a", delay=0.2, record=timeline),
        mock("b", capability=Capability.SOIL_ASSESSMENT, delay=0.2, record=timeline),
        mock("c", capability=Capability.MARKET_INTELLIGENCE, delay=0.2, record=timeline))
    ctx = context()
    plan = plan_for(registry, ctx, agent_names=["a", "b", "c"])
    check("all three are in one level", len(plan.levels) == 1, plan.describe())

    began = time.perf_counter()
    results = run(ExecutionEngine(), plan, ctx)
    elapsed = time.perf_counter() - began

    check("all three succeeded", all(r.ok for r in results.values()))
    check("they ran concurrently, not one after another", elapsed < 0.45,
          f"{elapsed:.2f}s for 3x0.2s")


@case
def test_unsafe_agent_does_not_run_concurrently():
    timeline: List = []
    registry = fresh(mock("safe_one", delay=0.05, record=timeline),
                     mock("exclusive", capability=Capability.SOIL_ASSESSMENT,
                          delay=0.05, concurrency_safe=False, record=timeline))
    ctx = context()
    plan = plan_for(registry, ctx, agent_names=["safe_one", "exclusive"])
    run(ExecutionEngine(), plan, ctx)

    starts = {name: t for name, kind, t in timeline if kind == "start"}
    ends = {name: t for name, kind, t in timeline if kind == "end"}
    check("the unsafe agent waits for the safe one to finish",
          starts["exclusive"] >= ends["safe_one"] - 1e-6)


@case
def test_concurrency_is_bounded():
    """With a cap of 2, six agents must not all start at once."""
    live = {"now": 0, "peak": 0}

    def tracked(name: str, capability) -> AgentSpec:
        async def execute(_context):
            live["now"] += 1
            live["peak"] = max(live["peak"], live["now"])
            await asyncio.sleep(0.05)
            live["now"] -= 1
            return {"ok": True}
        return AgentSpec(name=name, version="1", description="m",
                         capabilities=frozenset({capability}),
                         execute=execute, validate_output=passthrough)

    caps = list(Capability)
    registry = fresh(*[tracked(f"a{i}", caps[i % len(caps)]) for i in range(6)])
    ctx = context()
    plan = plan_for(registry, ctx, agent_names=[f"a{i}" for i in range(6)])
    run(ExecutionEngine(max_concurrency=2), plan, ctx)
    check("concurrency never exceeded the limit", live["peak"] <= 2, live["peak"])


# ── 3. Failure handling ─────────────────────────────────────────────────────

@case
def test_optional_failure_is_partial_success():
    registry = fresh(mock("weather"),
                     mock("market", capability=Capability.MARKET_INTELLIGENCE,
                          fails=ExternalServiceError("mandi API down"),
                          criticality=Criticality.BEST_EFFORT))
    ctx = context()
    plan = plan_for(registry, ctx, agent_names=["weather", "market"])
    results = run(ExecutionEngine(), plan, ctx)
    specs = {s.name: s for level in plan.levels for s in level}

    check("the healthy agent still answers", results["weather"].ok)
    check("the failed one is reported", results["market"].status == AgentStatus.FAILED)
    check("its error is categorised", results["market"].error_code == ErrorCode.EXTERNAL_SERVICE)
    check("overall is partial success",
          overall_status(results, specs) == OrchestrationStatus.PARTIAL_SUCCESS)


@case
def test_required_failure_fails_the_request():
    """A required agent's failure must not yield a confident half-answer."""
    registry = fresh(mock("weather", criticality=Criticality.REQUIRED,
                          fails=RuntimeError("provider exploded")),
                     mock("soil", capability=Capability.SOIL_ASSESSMENT))
    ctx = context()
    plan = plan_for(registry, ctx, agent_names=["weather", "soil"])
    results = run(ExecutionEngine(), plan, ctx)
    specs = {s.name: s for level in plan.levels for s in level}
    check("the request fails outright",
          overall_status(results, specs) == OrchestrationStatus.FAILED)


@case
def test_dependency_failure_skips_dependents_with_root_cause():
    registry = fresh(mock("a", fails=RuntimeError("boom")),
                     mock("b", capability=Capability.IRRIGATION_ADVICE, depends_on={"a"}),
                     mock("c", capability=Capability.WORK_PLAN, depends_on={"b"}))
    ctx = context()
    plan = plan_for(registry, ctx, agent_names=["a", "b", "c"])
    results = run(ExecutionEngine(), plan, ctx)

    check("the failing agent is failed", results["a"].status == AgentStatus.FAILED)
    check("its dependent is skipped, not failed",
          results["b"].status == AgentStatus.SKIPPED_DEPENDENCY_FAILED, results["b"].status)
    check("the skip names the cause", results["b"].caused_by == "a")
    check("the transitive dependent is also skipped",
          results["c"].status == AgentStatus.SKIPPED_DEPENDENCY_FAILED)
    check("the root cause is preserved through the chain",
          results["c"].caused_by == "a", results["c"].caused_by)


@case
def test_optional_dependency_failure_does_not_block():
    """An agent that only optionally depends on a failure still runs."""
    registry = fresh(mock("soil", capability=Capability.SOIL_ASSESSMENT,
                          fails=RuntimeError("sensor offline")),
                     mock("irrigation", capability=Capability.IRRIGATION_ADVICE,
                          optional_depends_on={"soil"}))
    ctx = context()
    plan = plan_for(registry, ctx, agent_names=["soil", "irrigation"])
    results = run(ExecutionEngine(), plan, ctx)
    check("the optional dependent still runs", results["irrigation"].ok,
          results["irrigation"].status)


@case
def test_independent_branch_continues_after_a_failure():
    registry = fresh(mock("a", fails=RuntimeError("boom")),
                     mock("b", capability=Capability.IRRIGATION_ADVICE, depends_on={"a"}),
                     mock("independent", capability=Capability.MARKET_INTELLIGENCE))
    ctx = context()
    plan = plan_for(registry, ctx, agent_names=["a", "b", "independent"])
    results = run(ExecutionEngine(), plan, ctx)
    check("the unrelated branch still answers", results["independent"].ok)


@case
def test_unexpected_exception_becomes_a_structured_failure():
    class Weird(Exception):
        pass

    registry = fresh(mock("odd", fails=Weird("something nobody predicted")))
    ctx = context()
    plan = plan_for(registry, ctx, agent_names=["odd"])
    results = run(ExecutionEngine(), plan, ctx)
    result = results["odd"]

    check("it is reported as failed", result.status == AgentStatus.FAILED)
    check("it gets the internal error code", result.error_code == ErrorCode.INTERNAL)
    check("the client message hides the exception",
          "nobody predicted" not in (result.error_message or ""), result.error_message)
    check("the message is written for a person",
          "odd" in (result.error_message or ""), result.error_message)


# ── 4. Timeouts ─────────────────────────────────────────────────────────────

@case
def test_timeout_is_bounded_and_recorded():
    registry = fresh(mock("slow", delay=2.0, timeout_s=0.15))
    ctx = context()
    plan = plan_for(registry, ctx, agent_names=["slow"])

    began = time.perf_counter()
    results = run(ExecutionEngine(), plan, ctx)
    elapsed = time.perf_counter() - began

    check("it stops at the timeout, not at the agent's own pace", elapsed < 1.0,
          f"{elapsed:.2f}s")
    check("the status is timeout", results["slow"].status == AgentStatus.TIMEOUT)
    check("the code is timeout", results["slow"].error_code == ErrorCode.TIMEOUT)


@case
def test_one_slow_agent_does_not_block_the_others():
    registry = fresh(mock("slow", delay=2.0, timeout_s=0.15),
                     mock("quick", capability=Capability.SOIL_ASSESSMENT))
    ctx = context()
    plan = plan_for(registry, ctx, agent_names=["slow", "quick"])
    results = run(ExecutionEngine(), plan, ctx)
    check("the fast agent still answers", results["quick"].ok)
    check("the slow one timed out", results["slow"].status == AgentStatus.TIMEOUT)


# ── 5. Retries ──────────────────────────────────────────────────────────────

@case
def test_transient_failure_succeeds_after_retry():
    spec = mock("flaky", fails=ExternalServiceError("temporary"), fail_times=1,
                retry=RetryPolicy(max_attempts=3, base_delay_s=0.01))
    registry = fresh(spec)
    ctx = context()
    plan = plan_for(registry, ctx, agent_names=["flaky"])
    results = run(ExecutionEngine(rng=random.Random(1)), plan, ctx)

    check("it eventually succeeds", results["flaky"].ok, results["flaky"].error_code)
    check("it took two attempts", results["flaky"].attempts == 2, results["flaky"].attempts)


@case
def test_retries_are_bounded():
    spec = mock("always_down", fails=ExternalServiceError("down"),
                retry=RetryPolicy(max_attempts=3, base_delay_s=0.01))
    registry = fresh(spec)
    ctx = context()
    plan = plan_for(registry, ctx, agent_names=["always_down"])
    results = run(ExecutionEngine(rng=random.Random(1)), plan, ctx)

    check("it gives up after the limit", results["always_down"].attempts == 3,
          results["always_down"].attempts)
    check("it ends as failed", results["always_down"].status == AgentStatus.FAILED)


@case
def test_deterministic_failures_are_not_retried():
    """Retrying bad input burns time and quota to fail identically."""
    for label, error in (("invalid input", AgentInputError("no location")),
                         ("invalid output", AgentOutputError("garbage"))):
        spec = mock(f"bad_{label.split()[1]}", fails=error,
                    retry=RetryPolicy(max_attempts=4, base_delay_s=0.01))
        registry = fresh(spec)
        ctx = context()
        plan = plan_for(registry, ctx, agent_names=[spec.name])
        results = run(ExecutionEngine(), plan, ctx)
        check(f"{label} is attempted only once", results[spec.name].attempts == 1,
              results[spec.name].attempts)


@case
def test_backoff_grows_and_is_jittered():
    policy = RetryPolicy(max_attempts=5, base_delay_s=1.0, max_delay_s=8.0, jitter=0.3)
    mid = [policy.delay_for(attempt, 0.5) for attempt in (1, 2, 3, 4)]
    check("delay grows exponentially", mid == [1.0, 2.0, 4.0, 8.0], mid)
    check("delay is capped", policy.delay_for(9, 0.5) == 8.0)
    low, high = policy.delay_for(1, 0.0), policy.delay_for(1, 0.999)
    check("jitter spreads the retries", low < 1.0 < high, (low, high))
    check("jitter never goes negative", policy.delay_for(1, 0.0) >= 0.0)


# ── 6. Output validation ────────────────────────────────────────────────────

@case
def test_malformed_output_is_rejected():
    def strict(raw: Any) -> NormalizedOutput:
        if not isinstance(raw, dict) or "forecast" not in raw:
            raise AgentOutputError("missing forecast")
        return NormalizedOutput(data=raw)

    registry = fresh(mock("liar", produces={"nonsense": True}, validate=strict))
    ctx = context()
    plan = plan_for(registry, ctx, agent_names=["liar"])
    results = run(ExecutionEngine(), plan, ctx)

    check("invalid output is not success",
          results["liar"].status == AgentStatus.INVALID_OUTPUT, results["liar"].status)
    check("it is coded as invalid output", results["liar"].error_code == ErrorCode.INVALID_OUTPUT)


@case
def test_invalid_output_is_not_passed_downstream():
    def strict(_raw: Any) -> NormalizedOutput:
        raise AgentOutputError("bad")

    seen: Dict[str, Any] = {}

    async def downstream(ctx: ExecutionContext):
        seen["upstream"] = ctx.output("upstream")
        return {"ok": True}

    upstream = mock("upstream", validate=strict)
    dependent = AgentSpec(name="downstream", version="1", description="m",
                          capabilities=frozenset({Capability.WORK_PLAN}),
                          execute=downstream, validate_output=passthrough,
                          optional_depends_on=frozenset({"upstream"}))
    registry = fresh(upstream, dependent)
    ctx = context()
    plan = plan_for(registry, ctx, agent_names=["upstream", "downstream"])
    run(ExecutionEngine(), plan, ctx)
    check("corrupted data never reaches the next agent", seen.get("upstream") is None,
          seen)


@case
def test_impossible_confidence_is_rejected():
    def overconfident(raw: Any) -> NormalizedOutput:
        return NormalizedOutput(data=raw, confidence=1.7)

    registry = fresh(mock("cocky", validate=overconfident))
    ctx = context()
    plan = plan_for(registry, ctx, agent_names=["cocky"])
    results = run(ExecutionEngine(), plan, ctx)
    check("a confidence outside 0-1 is invalid",
          results["cocky"].error_code == ErrorCode.INVALID_OUTPUT)


@case
def test_validator_returning_wrong_type_is_caught():
    registry = fresh(mock("sloppy", validate=lambda raw: {"not": "normalized"}))
    ctx = context()
    plan = plan_for(registry, ctx, agent_names=["sloppy"])
    results = run(ExecutionEngine(), plan, ctx)
    check("a bad validator fails the agent, not the request",
          results["sloppy"].error_code == ErrorCode.INVALID_OUTPUT)


# ── 7. Missing input ────────────────────────────────────────────────────────

@case
def test_agent_needing_absent_context_is_skipped_before_running():
    registry = fresh(mock("needs_soil", requires_context={"soil"}),
                     mock("needs_nothing", capability=Capability.MARKET_INTELLIGENCE))
    ctx = context(soil=None)
    plan = plan_for(registry, ctx, agent_names=["needs_soil", "needs_nothing"])

    check("it is not selected for execution", "needs_soil" not in plan.selected_names)
    check("the skip says what was missing",
          any(s.name == "needs_soil" and "soil" in s.missing for s in plan.skipped),
          plan.skipped)
    check("the other agent still runs", plan.selected_names == ["needs_nothing"])


@case
def test_dependent_of_unsatisfiable_agent_is_also_skipped():
    registry = fresh(mock("weather", requires_context={"location"}),
                     mock("irrigation", capability=Capability.IRRIGATION_ADVICE,
                          depends_on={"weather"}))
    ctx = ExecutionContext(request_id="r", location=None)
    plan = plan_for(registry, ctx, capabilities=[Capability.IRRIGATION_ADVICE])
    check("nothing is scheduled", plan.is_empty, plan.describe())
    names = {s.name for s in plan.skipped}
    check("both are reported as skipped", names == {"weather", "irrigation"}, names)


# ── 8. Registry safety ──────────────────────────────────────────────────────

@case
def test_circular_dependency_is_rejected():
    registry = AgentRegistry()
    registry.register(mock("a", depends_on={"b"}) if False else mock("a"))
    registry.register(mock("b", capability=Capability.SOIL_ASSESSMENT, depends_on={"a"}))
    try:
        registry.register(mock("a", depends_on={"b"}), replace=True)
        check("a cycle is refused", False, "no error raised")
    except RegistryError as exc:
        check("a cycle is refused", True)
        check("the error names the cycle", "Circular" in str(exc), str(exc))
    check("the catalog is left usable after the refusal",
          registry.get("a") is not None and not registry.get("a").depends_on)


@case
def test_unknown_dependency_is_rejected():
    registry = AgentRegistry()
    try:
        registry.register(mock("lonely", depends_on={"ghost"}))
        check("an unknown dependency is refused", False, "no error raised")
    except RegistryError as exc:
        check("an unknown dependency is refused", True)
        check("the error names the missing agent", "ghost" in str(exc), str(exc))


@case
def test_unknown_agent_name_cannot_execute():
    """The gate that stops a generated name from reaching execution."""
    registry = fresh(mock("real"))
    ctx = context()
    plan = plan_for(registry, ctx, agent_names=["real", "rm_rf", "definitely_not_an_agent"])
    check("only registered agents are planned", plan.selected_names == ["real"],
          plan.selected_names)


@case
def test_disabled_agent_is_not_executed():
    registry = fresh(mock("weather"), mock("market", capability=Capability.MARKET_INTELLIGENCE))
    registry.set_enabled("market", False)
    ctx = context()
    plan = plan_for(registry, ctx, agent_names=["weather", "market"])
    check("a disabled agent does not run", plan.selected_names == ["weather"],
          plan.selected_names)
    registry.set_enabled("market", True)
    plan_again = plan_for(registry, ctx, agent_names=["weather", "market"])
    check("it comes back when re-enabled", "market" in plan_again.selected_names)


@case
def test_capability_selection_needs_no_agent_names():
    registry = fresh(mock("weather"), mock("soil", capability=Capability.SOIL_ASSESSMENT))
    ctx = context(soil={"soil_ph": 7.0})
    plan = plan_for(registry, ctx, intents=[Intent.SOIL])
    check("an intent selects by capability", plan.selected_names == ["soil"],
          plan.selected_names)


# ── 9. Extensibility ────────────────────────────────────────────────────────

@case
def test_a_future_agent_runs_without_touching_the_engine():
    """The promise of the architecture: a new agent is a registration.

    Nothing in engine, planner, registry or aggregation is imported,
    subclassed or modified here - the agent is declared and it runs.
    """
    async def execute(ctx: ExecutionContext) -> Any:
        return {"pest": "aphid", "severity": 6.0,
                "from_weather": ctx.output("weather") is not None}

    def validate(raw: Any) -> NormalizedOutput:
        if not isinstance(raw, dict) or "severity" not in raw:
            raise AgentOutputError("no severity")
        return NormalizedOutput(data=raw, confidence=0.7, sources=["pest_model"])

    future_agent = AgentSpec(
        name="pest_disease_agent", version="0.1.0",
        description="A future agent, registered without engine changes.",
        capabilities=frozenset({Capability.KNOWLEDGE_ANSWER}),
        execute=execute, validate_output=validate,
        depends_on=frozenset({"weather"}),
        criticality=Criticality.OPTIONAL, timeout_s=3.0)

    registry = fresh(mock("weather"))
    registry.register(future_agent)

    ctx = context()
    plan = plan_for(registry, ctx, capabilities=[Capability.KNOWLEDGE_ANSWER])
    results = run(ExecutionEngine(), plan, ctx)

    check("the new agent ran", results["pest_disease_agent"].ok,
          results["pest_disease_agent"].error_message)
    check("its declared dependency ran first",
          plan.describe() == [["weather"], ["pest_disease_agent"]], plan.describe())
    check("it received the upstream output",
          results["pest_disease_agent"].output.data["from_weather"] is True)
    check("its confidence is carried through",
          results["pest_disease_agent"].output.confidence == 0.7)


# ── 10. Aggregation, provenance, conflicts ──────────────────────────────────

@case
def test_confidence_is_the_weakest_link():
    registry = fresh(
        mock("weather", validate=lambda r: NormalizedOutput(data=r, confidence=0.9)),
        mock("soil", capability=Capability.SOIL_ASSESSMENT,
             validate=lambda r: NormalizedOutput(data=r, confidence=0.4)))
    ctx = context()
    plan = plan_for(registry, ctx, agent_names=["weather", "soil"])
    results = run(ExecutionEngine(), plan, ctx)
    check("overall confidence is the lowest contributor",
          overall_confidence(results) == 0.4, overall_confidence(results))


@case
def test_provenance_lists_only_successful_agents():
    from AI_Backend.orchestration.contracts import AgentResult

    results = {
        "weather_watcher": AgentResult("weather_watcher", "1", AgentStatus.SUCCESS, 5.0,
                                       output=NormalizedOutput(data={}, confidence=0.8)),
        "soil_health": AgentResult("soil_health", "1", AgentStatus.FAILED, 5.0),
    }
    topics = {p.topic: p.agents for p in provenance(results)}
    check("the working agent is credited", topics.get("weather") == ["weather_watcher"])
    check("the failed agent is not credited",
          "soil_health" not in topics.get("soil", []), topics)


@case
def test_conflict_between_irrigation_and_rain_is_detected():
    from AI_Backend.orchestration import conflicts as rules

    ctx = context()
    ctx.outputs["irrigation_planner"] = NormalizedOutput(data={
        "irrigation_schedule": [{"date": "2026-06-15", "irrigation_required": True,
                                 "water_depth_mm": 30}]})
    ctx.outputs["weather_watcher"] = NormalizedOutput(data={
        "forecast_short_term": [{"date": "2026-06-15", "rainfall_mm": 40,
                                 "rain_probability_percent": 90}]})
    found = rules.detect(ctx)
    check("the conflict is found", len(found) == 1, found)
    conflict = found[0]
    check("both positions are recorded", len(conflict.positions) == 2)
    check("safety decides it", conflict.resolution.value == "safety", conflict.resolution)
    check("the farmer is told what to do", "hold" in conflict.farmer_note.lower(),
          conflict.farmer_note)


@case
def test_light_rain_is_not_treated_as_a_conflict():
    from AI_Backend.orchestration import conflicts as rules

    ctx = context()
    ctx.outputs["irrigation_planner"] = NormalizedOutput(data={
        "irrigation_schedule": [{"irrigation_required": True, "water_depth_mm": 30}]})
    ctx.outputs["weather_watcher"] = NormalizedOutput(data={
        "forecast_short_term": [{"rainfall_mm": 3, "rain_probability_percent": 90}]})
    check("3 mm against a 30 mm plan is no conflict", rules.detect(ctx) == [])


@case
def test_unresolvable_conflict_is_surfaced_not_decided():
    from AI_Backend.orchestration import conflicts as rules

    ctx = context(resources={"irrigation_available": False})
    ctx.outputs["crop_predictor"] = NormalizedOutput(data={
        "result": {"recommendations": [
            {"crop": "Sugarcane", "water_security": {"category": "irrigation_essential"}}]}})
    found = rules.detect(ctx)
    check("it is reported", len(found) == 1, found)
    check("no side is invented", found[0].resolution.value == "unresolved")
    check("the farmer decides", "cannot irrigate" in found[0].farmer_note.lower(),
          found[0].farmer_note)


@case
def test_a_broken_detector_cannot_break_the_response():
    from AI_Backend.orchestration import conflicts as rules

    def exploding(_ctx):
        raise RuntimeError("detector bug")

    rules.DETECTORS.append(exploding)
    try:
        check("a failing detector is contained", rules.detect(context()) == [])
    finally:
        rules.DETECTORS.remove(exploding)


@case
def test_summary_is_honest_about_what_is_missing():
    from AI_Backend.orchestration.contracts import AgentResult

    results = {
        "weather_watcher": AgentResult("weather_watcher", "1", AgentStatus.SUCCESS, 5.0,
                                       output=NormalizedOutput(data={})),
        "market_intelligence": AgentResult("market_intelligence", "1", AgentStatus.FAILED,
                                           5.0, error_code=ErrorCode.EXTERNAL_SERVICE),
    }
    text = summarise(OrchestrationStatus.PARTIAL_SUCCESS, results, [], [])
    check("the summary names the missing agent", "market_intelligence" in text, text)
    check("it states how many answered", "1 of 2" in text, text)


# ── 11. Logging and correlation ─────────────────────────────────────────────

@case
def test_lifecycle_events_carry_the_request_id():
    import logging as std_logging
    from AI_Backend.orchestration.observability import Event, emit

    captured: List[str] = []

    class Capture(std_logging.Handler):
        def emit(self, record):
            captured.append(record.getMessage())

    logger = std_logging.getLogger("farmxpert.orchestration")
    handler = Capture()
    logger.addHandler(handler)
    previous_level = logger.level
    logger.setLevel(std_logging.DEBUG)
    std_logging.disable(std_logging.NOTSET)
    try:
        emit(Event.AGENT_STARTED, "req-42", agent="weather", attempt=1)
        emit(Event.ORCHESTRATION_COMPLETED, "req-42", status="success")
    finally:
        logger.removeHandler(handler)
        logger.setLevel(previous_level)
        std_logging.disable(std_logging.CRITICAL)

    check("two events were logged", len(captured) == 2, captured)
    check("every line carries the request id",
          all("req-42" in line for line in captured), captured)
    check("the event name is in the line", "AGENT_STARTED" in captured[0], captured[0])


@case
def test_secrets_are_never_logged():
    import logging as std_logging
    from AI_Backend.orchestration.observability import Event, emit

    captured: List[str] = []

    class Capture(std_logging.Handler):
        def emit(self, record):
            captured.append(record.getMessage())

    logger = std_logging.getLogger("farmxpert.orchestration")
    handler = Capture()
    logger.addHandler(handler)
    previous_level = logger.level
    logger.setLevel(std_logging.DEBUG)
    std_logging.disable(std_logging.NOTSET)
    try:
        emit(Event.AGENT_STARTED, "req-1", agent="weather",
             api_key="nvapi-secret-value", farmer_phone="9876543210",
             config={"password": "hunter2", "model": "llama"})
    finally:
        logger.removeHandler(handler)
        logger.setLevel(previous_level)
        std_logging.disable(std_logging.CRITICAL)

    line = captured[0]
    for secret in ("nvapi-secret-value", "hunter2", "9876543210"):
        check(f"{secret[:6]}… is not logged", secret not in line, line)
    check("harmless fields survive", "weather" in line)


# ── 12. TOON encoding ───────────────────────────────────────────────────────

@case
def test_toon_is_shorter_than_json_and_keeps_numbers():
    import json

    payload = {"tasks": [
        {"title": "Irrigate", "date": "2026-06-15", "priority": "critical", "mm": 30.5},
        {"title": "Spray", "date": "2026-06-16", "priority": "high", "mm": 0.0},
        {"title": "Weed", "date": "2026-06-17", "priority": "medium", "mm": 0.0}]}
    toon = encode(payload)
    as_json = json.dumps(payload)

    check("TOON costs fewer tokens than JSON",
          estimate_tokens(toon) < estimate_tokens(as_json),
          f"{estimate_tokens(toon)} vs {estimate_tokens(as_json)}")
    check("the row count is declared", "tasks[3]" in toon, toon)
    check("the header appears once", toon.count("title") == 1, toon)
    check("numbers are unchanged", "30.5" in toon, toon)


@case
def test_toon_quotes_values_that_would_break_columns():
    encoded = encode({"rows": [{"note": "wait, then irrigate", "n": 1},
                               {"note": "spray early", "n": 2}]})
    check("a comma inside a value is quoted", '"wait, then irrigate"' in encoded, encoded)


@case
def test_toon_handles_awkward_input():
    check("empty values are omitted", encode({"a": None, "b": "", "c": []}) == "")
    deep: Dict[str, Any] = {}
    node = deep
    for i in range(30):
        node["next"] = {}
        node = node["next"]
    check("deep nesting terminates loudly", "OMITTED" in encode(deep), encode(deep)[-80:])
    mixed = encode({"items": [{"a": 1}, "plain", 3]})
    check("mixed lists still encode", "items[3]" in mixed, mixed)


# ── 13. End-to-end through the service, with mocks ──────────────────────────

@case
def test_service_returns_partial_success_with_full_accounting():
    from AI_Backend.orchestration.schemas import OrchestrationRequest
    from AI_Backend.orchestration.service import OrchestratorService

    registry = fresh(
        mock("weather"),
        mock("soil", capability=Capability.SOIL_ASSESSMENT, requires_context={"soil"}),
        mock("market", capability=Capability.MARKET_INTELLIGENCE,
             criticality=Criticality.BEST_EFFORT,
             fails=ExternalServiceError("mandi down")),
        mock("irrigation", capability=Capability.IRRIGATION_ADVICE,
             depends_on={"weather"}, requires_context={"crop"}))

    service = OrchestratorService(registry=registry)
    request = OrchestrationRequest(
        agents=["weather", "soil", "market", "irrigation"],
        location={"lat": 22.3, "lon": 70.8},
        crop={"name": "groundnut"})
    response = asyncio.run(service.run(request))

    check("status is partial success",
          response.status == OrchestrationStatus.PARTIAL_SUCCESS, response.status)
    check("successful results are returned",
          set(response.results) == {"weather", "irrigation"}, set(response.results))
    check("the failed agent is listed", "market" in response.failed, response.failed)
    check("the agent needing soil is skipped",
          any(s.name == "soil" for s in response.skipped), response.skipped)
    check("the skip says soil was missing",
          any("soil" in s.missing for s in response.skipped if s.name == "soil"))
    check("a warning explains the failure", any("market" in w for w in response.warnings),
          response.warnings)
    check("execution metadata is present",
          response.execution.agents_succeeded == 2 and response.execution.agents_failed == 1,
          response.execution)
    check("the request id is echoed", bool(response.request_id))
    check("no stack trace reaches the client",
          all("Traceback" not in (a.error or "") for a in response.agent_results))


@case
def test_service_reports_validation_error_when_nothing_can_run():
    from AI_Backend.orchestration.schemas import OrchestrationRequest
    from AI_Backend.orchestration.service import OrchestratorService

    registry = fresh(mock("weather", requires_context={"location"}))
    response = asyncio.run(OrchestratorService(registry=registry).run(
        OrchestrationRequest(agents=["weather"])))

    check("it is a validation error",
          response.status == OrchestrationStatus.VALIDATION_ERROR, response.status)
    check("the missing input is named", "location" in response.summary, response.summary)
    check("nothing was fabricated", response.results == {})


@case
def test_request_must_ask_for_something():
    from pydantic import ValidationError as PydanticError

    from AI_Backend.orchestration.schemas import OrchestrationRequest
    try:
        OrchestrationRequest(farm_id="F1")
        check("an empty request is rejected", False, "no error raised")
    except PydanticError:
        check("an empty request is rejected", True)


@case
def test_agent_names_are_bounded_before_lookup():
    from pydantic import ValidationError as PydanticError

    from AI_Backend.orchestration.schemas import OrchestrationRequest
    for bad in ("../../etc/passwd", "a" * 100, "drop;table"):
        try:
            OrchestrationRequest(agents=[bad])
            check(f"{bad[:12]}… is rejected", False, "accepted")
        except PydanticError:
            check(f"{bad[:12]}… is rejected", True)


# ── 14. The real catalog ────────────────────────────────────────────────────

@case
def test_the_real_catalog_is_valid():
    """The shipped agents form a usable graph - checked without running them."""
    from AI_Backend.orchestration.agents import _BUILDERS, register_all
    from AI_Backend.orchestration.registry import AgentRegistry

    registry = AgentRegistry()
    registered = register_all(registry)
    check("every shipped agent registers", registered == len(_BUILDERS),
          f"{registered} of {len(_BUILDERS)}")
    registry.validate()          # raises if the graph is broken
    check("the dependency graph is valid", True)

    names = registry.names()
    for expected in ("weather_watcher", "soil_health", "irrigation_planner",
                     "crop_predictor", "task_scheduler", "retrieval_agent"):
        check(f"{expected} is in the catalog", expected in names, sorted(names))

    irrigation = registry.require("irrigation_planner")
    check("irrigation depends on weather", "weather_watcher" in irrigation.depends_on)
    scheduler = registry.require("task_scheduler")
    check("the scheduler's dependencies are all optional",
          not scheduler.depends_on and scheduler.optional_depends_on,
          scheduler.depends_on)


@case
def test_real_plan_orders_the_real_agents_correctly():
    from AI_Backend.orchestration.agents import register_all
    from AI_Backend.orchestration.registry import AgentRegistry

    registry = AgentRegistry()
    register_all(registry)
    ctx = context(soil={"soil_ph": 7.5, "electrical_conductivity": 0.4},
                  crop={"name": "groundnut", "growth_stage": "flowering"})
    plan = Planner(registry).plan(ctx, intents=[Intent.DAILY_PLAN, Intent.IRRIGATION])
    levels = plan.describe()

    weather_level = next(i for i, l in enumerate(levels) if "weather_watcher" in l)
    irrigation_level = next(i for i, l in enumerate(levels) if "irrigation_planner" in l)
    scheduler_level = next(i for i, l in enumerate(levels) if "task_scheduler" in l)

    check("weather runs before irrigation", weather_level < irrigation_level, levels)
    check("the scheduler runs last", scheduler_level == len(levels) - 1, levels)
    check("independent agents share the first level", len(levels[0]) > 1, levels)


@case
def test_mcp_tools_come_from_the_registry():
    from AI_Backend.orchestration import mcp_server
    from AI_Backend.orchestration.agents import register_all
    from AI_Backend.orchestration.registry import REGISTRY

    register_all()
    tools = {t["name"] for t in mcp_server.tool_definitions()}
    check("every agent has a tool",
          all(f"farm_{name}" in tools for name in REGISTRY.names()), sorted(tools))
    check("the orchestration tool exists", "farm_orchestrate" in tools)
    check("the catalog tool exists", "farm_agents" in tools)
    check("every tool declares a schema",
          all("inputSchema" in t for t in mcp_server.tool_definitions()))

    async def unknown():
        try:
            await mcp_server.call_tool("farm_not_a_real_agent", {})
            return False
        except ValueError:
            return True
    check("an unknown tool is refused", asyncio.run(unknown()))


# ── 15. Deadline and failure isolation ──────────────────────────────────────

@case
def test_overall_deadline_is_respected():
    """The request has one budget; agents cannot spend more between them."""
    registry = fresh(mock("slow_a", delay=5.0, timeout_s=5.0),
                     mock("slow_b", capability=Capability.SOIL_ASSESSMENT,
                          delay=5.0, timeout_s=5.0),
                     mock("later", capability=Capability.WORK_PLAN,
                          depends_on={"slow_a"}, delay=5.0, timeout_s=5.0))
    ctx = context()
    plan = plan_for(registry, ctx, agent_names=["slow_a", "slow_b", "later"])

    began = time.perf_counter()
    results = asyncio.run(ExecutionEngine(deadline_s=0.3).run(plan, ctx))
    elapsed = time.perf_counter() - began

    check("the whole request honours the budget", elapsed < 1.5, f"{elapsed:.2f}s")
    check("every agent is accounted for", len(results) == 3, sorted(results))
    check("the blocked agent is reported, not lost",
          results["later"].error_code in (ErrorCode.TIMEOUT, ErrorCode.DEPENDENCY_FAILED),
          results["later"].error_code)


@case
def test_per_attempt_timeout_is_clamped_to_the_remaining_budget():
    """An agent with a 30 s timeout cannot overrun a 0.3 s request."""
    registry = fresh(mock("greedy", delay=30.0, timeout_s=30.0))
    ctx = context()
    plan = plan_for(registry, ctx, agent_names=["greedy"])

    began = time.perf_counter()
    results = asyncio.run(ExecutionEngine(deadline_s=0.3).run(plan, ctx))
    elapsed = time.perf_counter() - began

    check("it is cut off at the request budget", elapsed < 1.0, f"{elapsed:.2f}s")
    check("it is recorded as a timeout", results["greedy"].status == AgentStatus.TIMEOUT)


@case
def test_retries_stop_when_the_budget_is_gone():
    spec = mock("flaky", fails=ExternalServiceError("down"),
                retry=RetryPolicy(max_attempts=5, base_delay_s=0.2), timeout_s=0.1)
    registry = fresh(spec)
    ctx = context()
    plan = plan_for(registry, ctx, agent_names=["flaky"])
    results = asyncio.run(ExecutionEngine(deadline_s=0.35,
                                          rng=random.Random(2)).run(plan, ctx))
    check("it does not use all five attempts", results["flaky"].attempts < 5,
          results["flaky"].attempts)


@case
def test_one_agent_failing_does_not_abandon_its_siblings():
    """A sibling's exception must not leave other agents unawaited."""
    registry = fresh(mock("boom", fails=RuntimeError("immediate")),
                     mock("slower", capability=Capability.SOIL_ASSESSMENT, delay=0.15),
                     mock("slowest", capability=Capability.MARKET_INTELLIGENCE, delay=0.25))
    ctx = context()
    plan = plan_for(registry, ctx, agent_names=["boom", "slower", "slowest"])
    results = asyncio.run(ExecutionEngine().run(plan, ctx))

    check("all three produced a result", len(results) == 3, sorted(results))
    check("the slow siblings completed", results["slower"].ok and results["slowest"].ok)
    check("the failure is still recorded", results["boom"].status == AgentStatus.FAILED)


# ── 16. Prompt cost: projection and encoding ────────────────────────────────

@case
def test_projection_keeps_the_facts_and_drops_the_noise():
    from AI_Backend.orchestration.prompt_view import project

    payload = {"task_scheduler": {
        "headline": "1 urgent job today", "do_first": "Irrigate",
        "agent_version": "3.0.0", "processed_at": "2026-06-15T05:30:00Z",
        "data_quality": {"score": 0.9, "notes": ["sensor drift"]},
        "daily_plans": [{"plan_date": "2026-06-15", "tasks": [{"title": "Irrigate"}]}],
        "all_tasks": [{"title": "Irrigate", "priority": "critical",
                       "scheduled_start_time": "06:00", "why_now": "flowering stage",
                       "do": ["a", "b", "c"], "do_not": ["x", "y", "z"],
                       "metadata": {"internal": 1}}]}}
    view = project(payload)["task_scheduler"]

    check("the headline survives", view["headline"] == "1 urgent job today")
    check("the task and its time survive",
          view["tasks"][0]["scheduled_start_time"] == "06:00")
    check("the reason survives", view["tasks"][0]["why_now"] == "flowering stage")
    check("advice survives", view["tasks"][0]["do"][:1] == ["a"])
    check("diagnostics are dropped",
          "data_quality" not in view and "agent_version" not in view)
    check("duplicated daily_plans are dropped", "daily_plans" not in view)


@case
def test_projection_never_alters_a_number():
    from AI_Backend.orchestration.prompt_view import project

    payload = {"irrigation_planner": {"irrigation_schedule": [
        {"date": "2026-06-15", "irrigation_required": True, "water_depth_mm": 29.97,
         "duration_hours": 2.13, "method": "drip",
         "reasons": [{"code": "SOIL_BELOW_WILTING", "value": 134.79}]}]}}
    day = project(payload)["irrigation_planner"]["schedule"][0]
    check("the depth is byte-identical", day["water_depth_mm"] == 29.97, day)
    check("the duration is byte-identical", day["duration_hours"] == 2.13)
    check("the reason code survives", day["reasons"] == ["SOIL_BELOW_WILTING"])


@case
def test_unknown_agent_is_projected_safely():
    from AI_Backend.orchestration.prompt_view import project

    view = project({"future_agent": {"finding": "aphids", "severity": 6.5,
                                     "debug": {"x": 1}, "agent_version": "0.1"}})
    check("its facts survive", view["future_agent"]["severity"] == 6.5)
    check("its noise is dropped", "debug" not in view["future_agent"])


@case
def test_toon_never_drops_a_value():
    """The guarantee that matters: TOON is compact, not lossy.

    An earlier version tabulated uniform rows and silently dropped the nested
    fields of those rows - losing every do/do-not line on a task plan. Cheaper
    is only acceptable when nothing is lost.
    """
    payload = {"tasks": [
        {"title": "Irrigate", "priority": "critical", "mm": 30.5,
         "do": ["check moisture", "walk the line"],
         "do_not": ["do not irrigate before rain"]},
        {"title": "Spray", "priority": "high", "mm": 0.0,
         "do": ["wear gloves"],
         "do_not": ["do not spray above 30 C", "do not spray in wind"]}]}
    encoded = encode(payload)
    for phrase in ("check moisture", "walk the line", "do not irrigate before rain",
                   "wear gloves", "do not spray above 30 C", "do not spray in wind",
                   "30.5", "Irrigate", "Spray", "critical"):
        check(f"TOON keeps {phrase[:24]!r}", phrase in encoded, encoded[:200])


@case
def test_toon_still_tabulates_genuinely_flat_rows():
    payload = {"forecast": [
        {"date": "2026-06-15", "tmax": 34.0, "rain_mm": 0.0},
        {"date": "2026-06-16", "tmax": 31.0, "rain_mm": 40.0}]}
    encoded = encode(payload)
    check("flat rows still become a table",
          "forecast[2]{date,tmax,rain_mm}:" in encoded, encoded)
    check("the header appears once", encoded.count("tmax") == 1, encoded)


@case
def test_fact_format_is_chosen_by_measurement():
    import json as json_module

    from AI_Backend.orchestration.llm import build_facts
    from AI_Backend.orchestration.prompt_view import project

    tabular = {"weather_watcher": {"forecast": [
        {"date": f"2026-06-{d}", "temp_min_c": 25.0, "temp_max_c": 34.0,
         "rainfall_mm": 0.0, "rain_probability_percent": 10.0, "wind_speed_kmh": 8.0}
        for d in range(15, 20)]}}
    nested = {"soil_health": {"soil_health_score": 72, "summary": "Low nitrogen.",
                              "alerts": [{"type": "LOW_N", "severity": "high",
                                          "message": "Nitrogen is low."}]}}

    tab_text, tab_format = build_facts(tabular)
    nest_text, nest_format = build_facts(nested)
    check("a table is sent as TOON", tab_format == "toon", tab_format)
    check("a nested object is sent as JSON", nest_format == "json", nest_format)

    as_json = json_module.dumps(project(tabular), separators=(",", ":"), default=str)
    check("the chosen encoding is never the longer one", len(tab_text) <= len(as_json),
          f"{len(tab_text)} vs {len(as_json)}")
    check("facts are non-empty", bool(tab_text) and bool(nest_text))


@case
def test_prompt_cost_stays_bounded_for_a_full_farm_day():
    """A realistic all-agent payload must not blow the prompt budget."""
    from AI_Backend.orchestration.llm import build_facts

    results = {
        "weather_watcher": {"forecast_short_term": [
            {"date": f"2026-06-{d}", "temp_min_c": 25.0, "temp_max_c": 36.0,
             "rainfall_mm": 0.0, "rain_probability_percent": 5.0,
             "wind_speed_kmh": 9.0, "humidity_percent": 40.0} for d in range(15, 29)],
            "alerts": [{"type": "heat", "severity": "high", "message": "Hot week."}],
            "agro_advisory": {"summary": ["Work early."] * 10},
            "debug": {"provider_payload": "x" * 5000}},
        "task_scheduler": {"headline": "3 jobs", "all_tasks": [
            {"title": f"Task {i}", "category": "irrigation", "status": "scheduled",
             "priority": "high", "why_now": "because of moisture",
             "do": ["a"] * 6, "do_not": ["b"] * 6, "safety": ["c"] * 4,
             "metadata": {"noise": "y" * 400}} for i in range(12)],
            "daily_plans": [{"tasks": ["duplicate"] * 12}]},
    }
    facts, _ = build_facts(results)
    check("the prompt stays well under the budget",
          estimate_tokens(facts) < 2500, estimate_tokens(facts))
    check("the real facts survive", "Task 0" in facts and "3 jobs" in facts)
    check("provider debug never reaches the prompt", "xxxxx" not in facts)


# ── runner ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print(f"\n{len(PASSED) + len(FAILED)} checks\n")
    for failure in FAILED:
        print("  FAIL", failure)
    print(f"\n{len(PASSED)}/{len(PASSED) + len(FAILED)} checks passed\n")
    sys.exit(1 if FAILED else 0)
