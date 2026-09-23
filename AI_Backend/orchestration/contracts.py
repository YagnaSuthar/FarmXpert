"""
Orchestration contracts
========================
The types every part of the orchestration layer agrees on: what an agent is,
what running one produces, and how a failure is described.

Nothing here knows about farming, and nothing here knows the name of any
particular agent. That is the point: the engine works against these types, so
a new agent is a new registration, never a new branch in the engine.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Awaitable, Callable, Dict, FrozenSet, List, Optional, Set


# ── What an agent can contribute ────────────────────────────────────────────

class Capability(str, Enum):
    """What an agent produces, in the caller's terms.

    Requests ask for capabilities; the registry turns them into agents. A
    caller never has to know which agent answers a question, so agents can be
    replaced or split without changing any caller.
    """
    WEATHER_FORECAST   = "weather_forecast"
    SOIL_ASSESSMENT    = "soil_assessment"
    IRRIGATION_ADVICE  = "irrigation_advice"
    CROP_SELECTION     = "crop_selection"
    WORK_PLAN          = "work_plan"
    MARKET_INTELLIGENCE = "market_intelligence"
    KNOWLEDGE_ANSWER   = "knowledge_answer"


class Criticality(str, Enum):
    """What this agent's failure means for the whole request."""
    REQUIRED    = "required"      # no safe answer without it
    OPTIONAL    = "optional"      # dependents stop; independent branches go on
    BEST_EFFORT = "best_effort"   # a warning, nothing more


class AgentStatus(str, Enum):
    SUCCESS         = "success"
    FAILED          = "failed"
    TIMEOUT         = "timeout"
    SKIPPED         = "skipped"                    # inputs not available
    SKIPPED_DEPENDENCY_FAILED = "skipped_dependency_failed"
    INVALID_OUTPUT  = "invalid_output"
    CANCELLED       = "cancelled"


class OrchestrationStatus(str, Enum):
    SUCCESS          = "success"
    PARTIAL_SUCCESS  = "partial_success"
    FAILED           = "failed"
    VALIDATION_ERROR = "validation_error"


class ErrorCode(str, Enum):
    """Why something failed, in a form a client can branch on safely.

    A raw exception message can contain a connection string or a file path, so
    clients get one of these codes and a sentence written for them; the
    exception itself goes to the log with the request id.
    """
    VALIDATION_FAILED   = "validation_failed"     # the request was wrong
    MISSING_INPUT       = "missing_input"         # required context absent
    TIMEOUT             = "timeout"
    EXTERNAL_SERVICE    = "external_service"      # an upstream API failed
    RATE_LIMITED        = "rate_limited"
    DATABASE            = "database"
    MODEL_UNAVAILABLE   = "model_unavailable"     # ML artefact or LLM missing
    INVALID_OUTPUT      = "invalid_output"        # the agent returned nonsense
    DEPENDENCY_FAILED   = "dependency_failed"
    CANCELLED           = "cancelled"
    INTERNAL            = "internal"              # anything unexpected

    @property
    def retryable(self) -> bool:
        """Retry only what a second attempt could plausibly fix.

        A validation error or a malformed output is deterministic: retrying
        burns time and quota to fail identically.
        """
        return self in _RETRYABLE


_RETRYABLE: FrozenSet["ErrorCode"] = frozenset({
    ErrorCode.TIMEOUT,
    ErrorCode.EXTERNAL_SERVICE,
    ErrorCode.RATE_LIMITED,
    ErrorCode.DATABASE,
})


# ── Retry ───────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class RetryPolicy:
    """Bounded retries with exponential backoff and jitter.

    Jitter matters: without it, every farmer whose request hit the same
    upstream outage retries at the same instant and keeps it down.
    """
    max_attempts: int = 1          # 1 means "no retry"
    base_delay_s: float = 0.5
    max_delay_s: float = 4.0
    jitter: float = 0.3            # +/- this fraction of the delay

    def delay_for(self, attempt: int, random_unit: float) -> float:
        """Seconds to wait before `attempt` (1-based). `random_unit` in [0,1)."""
        raw = min(self.base_delay_s * (2 ** max(0, attempt - 1)), self.max_delay_s)
        spread = raw * self.jitter
        return max(0.0, raw - spread + 2 * spread * random_unit)


NO_RETRY = RetryPolicy(max_attempts=1)


# ── Execution context ───────────────────────────────────────────────────────

@dataclass
class ExecutionContext:
    """What the request knows, plus what agents have produced so far.

    Agents read from it and never write to it: the engine writes results, so
    there is one place where data enters the shared state and one place to look
    when it is wrong. Secrets are never stored here.
    """
    request_id: str
    farm_id: Optional[str] = None
    farmer_query: Optional[str] = None
    language: str = "en"

    # Request-supplied facts (the "context" agents declare requirements against)
    location: Optional[Dict[str, float]] = None          # {"lat":…, "lon":…}
    soil: Optional[Dict[str, Any]] = None
    crop: Optional[Dict[str, Any]] = None
    resources: Optional[Dict[str, Any]] = None
    market: Optional[Dict[str, Any]] = None
    extras: Dict[str, Any] = field(default_factory=dict)

    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    outputs: Dict[str, "NormalizedOutput"] = field(default_factory=dict)

    def available_context(self) -> Set[str]:
        """Which declared context keys the caller actually provided."""
        present = set()
        for key in ("location", "soil", "crop", "resources", "market"):
            if getattr(self, key):
                present.add(key)
        if self.farm_id:
            present.add("farm_id")
        if self.farmer_query:
            present.add("farmer_query")
        present.update(k for k, v in self.extras.items() if v is not None)
        return present

    def output(self, agent_name: str) -> Optional[Any]:
        """The validated data an agent produced, or None if it has none."""
        found = self.outputs.get(agent_name)
        return found.data if found else None


# ── Agent output ────────────────────────────────────────────────────────────

@dataclass
class NormalizedOutput:
    """An agent's result after validation.

    `confidence` and `freshness_s` are only set when the agent genuinely
    reports them. An unknown value stays None rather than being guessed, so a
    cached three-hour-old forecast is never presented as fresh.
    """
    data: Any
    confidence: Optional[float] = None          # 0-1
    produced_at: Optional[datetime] = None
    freshness_s: Optional[float] = None         # age of the underlying data
    sources: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


@dataclass
class AgentResult:
    """One agent's execution, as reported to the caller and the logs."""
    name: str
    version: str
    status: AgentStatus
    duration_ms: float
    attempts: int = 1
    execution_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    output: Optional[NormalizedOutput] = None
    error_code: Optional[ErrorCode] = None
    error_message: Optional[str] = None        # written for a human, never a trace
    caused_by: Optional[str] = None            # the agent whose failure skipped this one
    finished_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def ok(self) -> bool:
        return self.status == AgentStatus.SUCCESS


# ── The agent specification ─────────────────────────────────────────────────

ExecuteFn = Callable[[ExecutionContext], Awaitable[Any]]
ValidateFn = Callable[[Any], NormalizedOutput]


@dataclass(frozen=True)
class AgentSpec:
    """Everything the orchestrator needs to know about one agent.

    `requires_context` is what the CALLER must supply; `depends_on` is what
    another AGENT must produce. Keeping them apart is what lets the planner
    decide, before running anything, whether an agent can work at all.
    """
    name: str
    version: str
    description: str
    capabilities: FrozenSet[Capability]
    execute: ExecuteFn
    validate_output: ValidateFn

    requires_context: FrozenSet[str] = frozenset()
    optional_context: FrozenSet[str] = frozenset()
    depends_on: FrozenSet[str] = frozenset()
    optional_depends_on: FrozenSet[str] = frozenset()

    criticality: Criticality = Criticality.OPTIONAL
    timeout_s: float = 15.0
    retry: RetryPolicy = NO_RETRY
    concurrency_safe: bool = True
    enabled: bool = True

    # Documentation for the MCP tool generated from this agent.
    input_schema: Optional[Dict[str, Any]] = None

    @property
    def all_dependencies(self) -> FrozenSet[str]:
        return self.depends_on | self.optional_depends_on

    def missing_context(self, available: Set[str]) -> Set[str]:
        return set(self.requires_context) - available


class Timer:
    """Monotonic stopwatch in milliseconds - immune to clock changes."""

    def __init__(self) -> None:
        self._start = time.perf_counter()

    @property
    def ms(self) -> float:
        return (time.perf_counter() - self._start) * 1000.0
