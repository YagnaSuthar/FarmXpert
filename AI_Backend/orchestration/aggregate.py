"""
Result aggregation
===================
Turns raw agent results into the response a caller sees: overall status,
provenance, confidence, and a summary that is honest about what is missing.

Two rules govern everything here:

  * Nothing is invented. An agent that did not run contributes nothing, and
    its absence is stated rather than smoothed over.
  * Confidence is the weakest link. A recommendation built on a low-confidence
    input is not more trustworthy than that input.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence

from AI_Backend.orchestration.conflicts import Conflict
from AI_Backend.orchestration.contracts import (
    AgentResult,
    AgentSpec,
    AgentStatus,
    Criticality,
    OrchestrationStatus,
)
from AI_Backend.orchestration.planner import ExecutionPlan, SkippedAgent
from AI_Backend.orchestration.schemas import (
    AgentResultOut,
    ConflictOut,
    ExecutionOut,
    ProvenanceOut,
    SkippedOut,
)

# A failure is one of these three, everywhere. Matching on status name
# prefixes worked but would break the moment a status was renamed, and a
# misclassified failure is one that quietly disappears from the response.
FAILURE_STATUSES = frozenset({AgentStatus.FAILED, AgentStatus.TIMEOUT,
                              AgentStatus.INVALID_OUTPUT})
SKIPPED_STATUSES = frozenset({AgentStatus.SKIPPED,
                              AgentStatus.SKIPPED_DEPENDENCY_FAILED})


def failed_agents(results: Dict[str, AgentResult]) -> List[str]:
    """Agents that failed on their own account, not because another did.

    A dependency casualty belongs in `skipped` with its root cause; listing it
    here would send whoever is debugging to the wrong agent.
    """
    return sorted(name for name, result in results.items()
                  if result.status in FAILURE_STATUSES and result.caused_by is None)


# Which agents stand behind each part of an answer. Declared here rather than
# inferred, so provenance stays true even when an agent is added or replaced.
TOPIC_CONTRIBUTORS: Dict[str, Sequence[str]] = {
    "irrigation":  ("irrigation_planner", "weather_watcher", "soil_health"),
    "crop_choice": ("crop_predictor", "soil_health", "weather_watcher"),
    "work_plan":   ("task_scheduler", "irrigation_planner", "soil_health",
                    "weather_watcher", "crop_predictor"),
    "soil":        ("soil_health",),
    "weather":     ("weather_watcher",),
    "market":      ("market_intelligence",),
    "knowledge":   ("retrieval_agent",),
}


def overall_status(results: Dict[str, AgentResult],
                   specs: Dict[str, AgentSpec]) -> OrchestrationStatus:
    """Success only when everything that mattered worked.

    A failed REQUIRED agent fails the request outright: a recommendation
    missing an input it was defined to need would be misleading, and a
    misleading farm recommendation is worse than no answer.
    """
    if not results:
        return OrchestrationStatus.FAILED

    for name, result in results.items():
        spec = specs.get(name)
        if spec and spec.criticality == Criticality.REQUIRED and not result.ok:
            return OrchestrationStatus.FAILED

    succeeded = [r for r in results.values() if r.ok]
    if not succeeded:
        return OrchestrationStatus.FAILED
    if len(succeeded) == len(results):
        return OrchestrationStatus.SUCCESS
    return OrchestrationStatus.PARTIAL_SUCCESS


def successful_outputs(results: Dict[str, AgentResult]) -> Dict[str, object]:
    return {name: r.output.data for name, r in results.items()
            if r.ok and r.output is not None}


def to_agent_results(results: Dict[str, AgentResult]) -> List[AgentResultOut]:
    out: List[AgentResultOut] = []
    for result in sorted(results.values(), key=lambda r: r.name):
        output = result.output
        out.append(AgentResultOut(
            name=result.name,
            version=result.version,
            status=result.status,
            duration_ms=round(result.duration_ms, 2),
            attempts=result.attempts,
            execution_id=result.execution_id,
            result=output.data if output else None,
            confidence=output.confidence if output else None,
            data_age_seconds=output.freshness_s if output else None,
            sources=list(output.sources) if output else [],
            warnings=list(output.warnings) if output else [],
            error_code=result.error_code,
            error=result.error_message,
            caused_by=result.caused_by,
            finished_at=result.finished_at))
    return out


def to_skipped(plan_skipped: Sequence[SkippedAgent],
               results: Dict[str, AgentResult]) -> List[SkippedOut]:
    """Everything that did not run, with the reason it did not."""
    out = [SkippedOut(name=s.name, reason=s.reason, missing=list(s.missing))
           for s in plan_skipped]
    for result in results.values():
        if result.status in SKIPPED_STATUSES:
            out.append(SkippedOut(
                name=result.name,
                reason=(f"Could not run because {result.caused_by} failed."
                        if result.caused_by else "Did not run."),
                caused_by=result.caused_by))
    return sorted(out, key=lambda s: s.name)


def to_conflicts(conflicts: Sequence[Conflict]) -> List[ConflictOut]:
    return [ConflictOut(
        topic=c.topic, description=c.description, positions=dict(c.positions),
        resolution=c.resolution.value, chosen=c.chosen, rationale=c.rationale,
        farmer_note=c.farmer_note, agents=list(c.agents)) for c in conflicts]


def provenance(results: Dict[str, AgentResult]) -> List[ProvenanceOut]:
    """For each part of the answer, the agents that actually contributed.

    Only successful agents are listed: provenance that credits an agent which
    failed would be worse than none at all.
    """
    out: List[ProvenanceOut] = []
    for topic, candidates in TOPIC_CONTRIBUTORS.items():
        contributors = [name for name in candidates
                        if name in results and results[name].ok]
        if not contributors:
            continue
        outputs = [results[name].output for name in contributors if results[name].output]
        confidences = [o.confidence for o in outputs if o and o.confidence is not None]
        produced = [o.produced_at for o in outputs if o and o.produced_at]
        out.append(ProvenanceOut(
            topic=topic,
            agents=contributors,
            produced_at=max(produced) if produced else None,
            confidence=min(confidences) if confidences else None))
    return out


def overall_confidence(results: Dict[str, AgentResult]) -> Optional[float]:
    """The weakest contributing confidence, or None if nobody reported one."""
    values = [r.output.confidence for r in results.values()
              if r.ok and r.output and r.output.confidence is not None]
    return round(min(values), 3) if values else None


def execution_summary(plan: ExecutionPlan, results: Dict[str, AgentResult],
                      started_at, duration_ms: float) -> ExecutionOut:
    return ExecutionOut(
        started_at=started_at,
        duration_ms=round(duration_ms, 2),
        levels=plan.describe(),
        agents_run=len(results),
        agents_succeeded=sum(1 for r in results.values() if r.ok),
        agents_failed=sum(1 for r in results.values() if r.status in FAILURE_STATUSES),
        agents_skipped=sum(1 for r in results.values() if r.status in SKIPPED_STATUSES))


def summarise(status: OrchestrationStatus,
              results: Dict[str, AgentResult],
              skipped: Sequence[SkippedOut],
              conflicts: Sequence[Conflict]) -> str:
    """One honest sentence. Names what is missing instead of hiding it."""
    ok = sorted(name for name, r in results.items() if r.ok)
    bad = failed_agents(results)

    if status == OrchestrationStatus.FAILED:
        reason = f" {bad[0]} could not run" if bad else ""
        return f"No reliable answer could be produced.{reason}."

    parts = [f"{len(ok)} of {len(results)} agents answered"]
    if bad:
        parts.append(f"{', '.join(bad)} unavailable")
    if skipped:
        parts.append(f"{len(skipped)} skipped for missing information")
    if conflicts:
        unresolved = [c for c in conflicts if c.resolution.value == "unresolved"]
        parts.append(f"{len(conflicts)} conflict(s) found"
                     + (f", {len(unresolved)} needing your decision" if unresolved else ""))
    return "; ".join(parts) + "."


def warnings_for(results: Dict[str, AgentResult],
                 specs: Dict[str, AgentSpec]) -> List[str]:
    """Things the caller should know but that did not stop the request."""
    out: List[str] = []
    for name, result in sorted(results.items()):
        if result.ok:
            if result.output:
                out.extend(result.output.warnings)
            continue
        if result.status in SKIPPED_STATUSES:
            continue
        spec = specs.get(name)
        if spec and spec.criticality == Criticality.BEST_EFFORT:
            out.append(f"{name} was unavailable; the answer does not include it.")
        else:
            out.append(f"{name} failed ({result.error_code.value if result.error_code else 'unknown'}); "
                       "its part of the answer is missing rather than estimated.")
    return out
