"""
Execution engine
=================
Runs a plan: concurrency inside a level, order between levels, a bounded
timeout and bounded retries per agent, and a failure policy that decides what
a failure costs the rest of the request.

The engine never names an agent. Everything it does is driven by the metadata
on the AgentSpec, which is why a new agent needs no change here.
"""

from __future__ import annotations

import asyncio
import os
import random
import time
from typing import Dict, List, Optional, Sequence

from AI_Backend.orchestration.contracts import (
    AgentResult,
    AgentSpec,
    AgentStatus,
    Criticality,
    ErrorCode,
    ExecutionContext,
    NormalizedOutput,
    Timer,
)
from AI_Backend.orchestration.observability import Event, emit, log_exception, safe_message
from AI_Backend.orchestration.planner import ExecutionPlan

DEFAULT_MAX_CONCURRENCY = 8
# A farmer is waiting. Past this the answer is worth less than the wait, so
# what has finished is returned and the rest is reported as out of time.
DEFAULT_DEADLINE_S = float(os.getenv("FARMXPERT_ORCHESTRATION_DEADLINE_S", "30"))


class AgentInputError(ValueError):
    """The agent was called with input it cannot work with.

    Deterministic, so it is never retried. Adapters raise it instead of
    letting a ValidationError surface as an unexplained internal error.
    """


class AgentOutputError(ValueError):
    """The agent returned something that failed validation."""


class ExternalServiceError(RuntimeError):
    """An upstream provider failed in a way a retry might survive."""


class ExecutionEngine:
    """Executes a plan and returns one AgentResult per agent."""

    def __init__(self, *, max_concurrency: int = DEFAULT_MAX_CONCURRENCY,
                 deadline_s: float = DEFAULT_DEADLINE_S,
                 rng: Optional[random.Random] = None) -> None:
        self.max_concurrency = max_concurrency
        self.deadline_s = deadline_s
        # Injectable so tests can make backoff deterministic.
        self._rng = rng or random.Random()

    async def run(self, plan: ExecutionPlan,
                  context: ExecutionContext,
                  *, deadline_s: Optional[float] = None) -> Dict[str, AgentResult]:
        results: Dict[str, AgentResult] = {}
        semaphore = asyncio.Semaphore(self.max_concurrency)
        # One deadline for the whole request. Without it the worst case is the
        # sum of every agent's timeout times its retries - on this catalog
        # about 80 seconds, which no farmer waits for. Every per-attempt
        # timeout is clamped to what is left of this budget.
        deadline = time.monotonic() + (deadline_s or self.deadline_s)

        for level in plan.levels:
            runnable, blocked = self._split_on_dependencies(level, results)
            results.update(blocked)

            if not runnable:
                continue

            if time.monotonic() >= deadline:
                self._mark_out_of_time(plan, results)
                emit(Event.ORCHESTRATION_FAILED, context.request_id,
                     reason="deadline_exhausted", pending=[s.name for s in runnable])
                break

            if len(runnable) == 1:
                produced = [await self._execute(runnable[0], context, semaphore, deadline)]
            else:
                # An agent that is not concurrency safe gets the level to
                # itself; the rest of the level still runs together.
                serial = [s for s in runnable if not s.concurrency_safe]
                parallel = [s for s in runnable if s.concurrency_safe]
                produced = []
                if parallel:
                    # return_exceptions keeps one sibling's failure from
                    # abandoning the others mid-flight; _execute already turns
                    # every ordinary error into a result, so anything arriving
                    # here is cancellation or a bug, and both are handled.
                    settled = await asyncio.gather(
                        *(self._execute(spec, context, semaphore, deadline)
                          for spec in parallel),
                        return_exceptions=True)
                    produced.extend(self._settle(parallel, settled, context))
                for spec in serial:
                    produced.append(await self._execute(spec, context, semaphore, deadline))

            for result in produced:
                results[result.name] = result
                if result.ok and result.output is not None:
                    # Only validated output becomes visible downstream.
                    context.outputs[result.name] = result.output

            fatal = self._critical_failure(runnable, produced)
            if fatal:
                emit(Event.DEPENDENCY_FAILED, context.request_id, agent=fatal,
                     reason="required_agent_failed")
                self._mark_remaining_skipped(plan, results, caused_by=fatal)
                break

        return results

    def _settle(self, specs: Sequence[AgentSpec], settled: Sequence,
                context: ExecutionContext) -> List[AgentResult]:
        """Turn gathered outcomes into results, preserving cancellation."""
        out: List[AgentResult] = []
        for spec, outcome in zip(specs, settled):
            if isinstance(outcome, AgentResult):
                out.append(outcome)
                continue
            if isinstance(outcome, asyncio.CancelledError):
                # The caller disconnected: stop, do not dress it up as a result.
                raise outcome
            log_exception(context.request_id, spec.name, outcome)
            out.append(AgentResult(
                name=spec.name, version=spec.version, status=AgentStatus.FAILED,
                duration_ms=0.0, error_code=ErrorCode.INTERNAL,
                error_message=safe_message(ErrorCode.INTERNAL, spec.name)))
        return out

    @staticmethod
    def _mark_out_of_time(plan: ExecutionPlan, results: Dict[str, AgentResult]) -> None:
        """Everything still pending when the budget ran out.

        Reported as a timeout rather than a failure: nothing is wrong with
        these agents, there was simply no time left for them.
        """
        for level in plan.levels:
            for spec in level:
                if spec.name in results:
                    continue
                results[spec.name] = AgentResult(
                    name=spec.name, version=spec.version, status=AgentStatus.TIMEOUT,
                    duration_ms=0.0, error_code=ErrorCode.TIMEOUT,
                    error_message=(f"{spec.name} did not run: the request reached its "
                                   "overall time limit first."))

    # ── dependency gating ───────────────────────────────────────────────

    def _split_on_dependencies(self, level: Sequence[AgentSpec],
                               results: Dict[str, AgentResult]):
        """Hold back agents whose required dependency did not succeed.

        They are recorded as SKIPPED_DEPENDENCY_FAILED with the root cause
        named - not as "failed", which would send whoever is debugging to the
        wrong agent entirely.
        """
        runnable: List[AgentSpec] = []
        blocked: Dict[str, AgentResult] = {}

        for spec in level:
            broken = [dep for dep in sorted(spec.depends_on)
                      if dep in results and not results[dep].ok]
            missing = [dep for dep in sorted(spec.depends_on) if dep not in results]
            cause = broken or missing
            if not cause:
                runnable.append(spec)
                continue

            root = self._root_cause(cause[0], results)
            blocked[spec.name] = AgentResult(
                name=spec.name, version=spec.version,
                status=AgentStatus.SKIPPED_DEPENDENCY_FAILED,
                duration_ms=0.0,
                error_code=ErrorCode.DEPENDENCY_FAILED,
                error_message=safe_message(ErrorCode.DEPENDENCY_FAILED, spec.name),
                caused_by=root)
        return runnable, blocked

    @staticmethod
    def _root_cause(name: str, results: Dict[str, AgentResult]) -> str:
        """Follow the chain back to the agent that actually failed."""
        seen = set()
        current = name
        while current in results and results[current].caused_by and current not in seen:
            seen.add(current)
            current = results[current].caused_by  # type: ignore[assignment]
        return current

    @staticmethod
    def _critical_failure(level: Sequence[AgentSpec],
                          produced: Sequence[AgentResult]) -> Optional[str]:
        """The name of a REQUIRED agent that failed, if there is one.

        A REQUIRED agent is one without which no safe answer exists. When one
        fails the run stops rather than assembling a recommendation from a
        hole - a half-answer about irrigation is worse than an honest refusal.
        """
        criticality = {spec.name: spec.criticality for spec in level}
        for result in produced:
            if not result.ok and criticality.get(result.name) == Criticality.REQUIRED:
                return result.name
        return None

    @staticmethod
    def _mark_remaining_skipped(plan: ExecutionPlan,
                                results: Dict[str, AgentResult],
                                caused_by: str) -> None:
        """Everything not yet run is skipped, naming the agent responsible."""
        for level in plan.levels:
            for spec in level:
                if spec.name in results:
                    continue
                results[spec.name] = AgentResult(
                    name=spec.name, version=spec.version,
                    status=AgentStatus.SKIPPED_DEPENDENCY_FAILED,
                    duration_ms=0.0,
                    error_code=ErrorCode.DEPENDENCY_FAILED,
                    error_message=safe_message(ErrorCode.DEPENDENCY_FAILED, spec.name),
                    caused_by=caused_by)

    # ── one agent ───────────────────────────────────────────────────────

    async def _execute(self, spec: AgentSpec, context: ExecutionContext,
                       semaphore: asyncio.Semaphore,
                       deadline: Optional[float] = None) -> AgentResult:
        """Run one agent with its timeout, retries and validation."""
        timer = Timer()
        result = AgentResult(name=spec.name, version=spec.version,
                             status=AgentStatus.FAILED, duration_ms=0.0)
        attempts = 0
        last_code = ErrorCode.INTERNAL

        for attempt in range(1, max(1, spec.retry.max_attempts) + 1):
            attempts = attempt
            emit(Event.AGENT_STARTED, context.request_id, agent=spec.name,
                 execution_id=result.execution_id, attempt=attempt,
                 timeout_s=spec.timeout_s)

            try:
                async with semaphore:
                    # Never let one agent's timeout outlive the whole request.
                    budget = spec.timeout_s
                    if deadline is not None:
                        budget = min(budget, max(0.0, deadline - time.monotonic()))
                    if budget <= 0:
                        raise asyncio.TimeoutError
                    raw = await asyncio.wait_for(spec.execute(context), timeout=budget)
                output = self._validate(spec, raw)

            except asyncio.TimeoutError:
                last_code = ErrorCode.TIMEOUT
                emit(Event.AGENT_TIMEOUT, context.request_id, agent=spec.name,
                     execution_id=result.execution_id, attempt=attempt,
                     timeout_s=spec.timeout_s)

            except asyncio.CancelledError:
                # The caller went away. Record it and let cancellation win.
                result.status = AgentStatus.CANCELLED
                result.error_code = ErrorCode.CANCELLED
                result.error_message = safe_message(ErrorCode.CANCELLED, spec.name)
                result.duration_ms = timer.ms
                result.attempts = attempts
                raise

            except AgentInputError as exc:
                last_code = ErrorCode.MISSING_INPUT
                log_exception(context.request_id, spec.name, exc)

            except AgentOutputError as exc:
                last_code = ErrorCode.INVALID_OUTPUT
                emit(Event.AGENT_OUTPUT_INVALID, context.request_id, agent=spec.name,
                     execution_id=result.execution_id, reason=str(exc)[:160])

            except ExternalServiceError as exc:
                last_code = ErrorCode.EXTERNAL_SERVICE
                log_exception(context.request_id, spec.name, exc)

            except Exception as exc:  # noqa: BLE001 - orchestration boundary
                # Anything unexpected becomes a structured failure. It is
                # logged in full here, and the client sees only a code.
                last_code = _classify(exc)
                log_exception(context.request_id, spec.name, exc)

            else:
                result.status = AgentStatus.SUCCESS
                result.output = output
                result.error_code = None
                result.duration_ms = timer.ms
                result.attempts = attempts
                emit(Event.AGENT_COMPLETED, context.request_id, agent=spec.name,
                     execution_id=result.execution_id, attempt=attempt,
                     duration_ms=round(result.duration_ms, 1),
                     confidence=output.confidence)
                return result

            # Retry only what a second attempt could fix, and only if any left.
            out_of_time = deadline is not None and time.monotonic() >= deadline
            if attempt < spec.retry.max_attempts and last_code.retryable and not out_of_time:
                delay = spec.retry.delay_for(attempt, self._rng.random())
                emit(Event.AGENT_RETRY, context.request_id, agent=spec.name,
                     execution_id=result.execution_id, attempt=attempt,
                     error_code=last_code, delay_s=round(delay, 3))
                await asyncio.sleep(delay)
                continue
            break

        result.attempts = attempts
        result.duration_ms = timer.ms
        result.error_code = last_code
        result.error_message = safe_message(last_code, spec.name)
        result.status = (AgentStatus.TIMEOUT if last_code == ErrorCode.TIMEOUT
                         else AgentStatus.INVALID_OUTPUT
                         if last_code == ErrorCode.INVALID_OUTPUT
                         else AgentStatus.FAILED)
        emit(Event.AGENT_FAILED, context.request_id, agent=spec.name,
             execution_id=result.execution_id, attempts=attempts,
             error_code=last_code, criticality=spec.criticality,
             duration_ms=round(result.duration_ms, 1))
        return result

    @staticmethod
    def _validate(spec: AgentSpec, raw) -> NormalizedOutput:
        """Never trust an agent's return value.

        A malformed result is a failure of that agent, not of the request: it
        is recorded and withheld from downstream agents rather than quietly
        corrupting whatever runs next.
        """
        try:
            output = spec.validate_output(raw)
        except AgentOutputError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise AgentOutputError(str(exc)) from exc
        if not isinstance(output, NormalizedOutput):
            raise AgentOutputError(
                f"{spec.name} validator returned {type(output).__name__}, "
                "expected NormalizedOutput.")
        if output.confidence is not None and not 0.0 <= output.confidence <= 1.0:
            raise AgentOutputError(
                f"{spec.name} reported confidence {output.confidence}, outside 0-1.")
        return output


def _classify(exc: BaseException) -> ErrorCode:
    """Map an unexpected exception onto a stable error code.

    Matching is on type names rather than imports so the orchestration layer
    does not depend on httpx, SQLAlchemy or any ML library being installed.
    """
    name = type(exc).__name__
    module = type(exc).__module__.split(".")[0]

    if module == "httpx" or "Timeout" in name:
        return ErrorCode.TIMEOUT if "Timeout" in name else ErrorCode.EXTERNAL_SERVICE
    if module in {"sqlalchemy", "asyncpg", "psycopg2"}:
        return ErrorCode.DATABASE
    if name in {"ValidationError", "ValueError", "TypeError", "KeyError"}:
        return ErrorCode.INVALID_OUTPUT
    if name in {"FileNotFoundError", "ModuleNotFoundError", "ImportError"}:
        return ErrorCode.MODEL_UNAVAILABLE
    if "RateLimit" in name or "TooManyRequests" in name:
        return ErrorCode.RATE_LIMITED
    if isinstance(exc, ConnectionError):
        return ErrorCode.EXTERNAL_SERVICE
    return ErrorCode.INTERNAL
