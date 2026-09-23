"""
Orchestration API contract
===========================
What a caller sends and what they get back. Deliberately stable: agents can
be added, replaced or renamed behind these models without a client change.

Nothing here carries an exception, a traceback or a configuration value - a
client gets an error code and a sentence written for a person.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from AI_Backend.orchestration.contracts import (
    AgentStatus,
    Capability,
    ErrorCode,
    OrchestrationStatus,
)
from AI_Backend.orchestration.planner import Intent


# ── request ─────────────────────────────────────────────────────────────────

class LocationInput(BaseModel):
    lat: float = Field(..., ge=-90.0, le=90.0)
    lon: float = Field(..., ge=-180.0, le=180.0)


class HistoryTurn(BaseModel):
    role: str = Field(..., pattern="^(farmer|assistant)$")
    content: str = Field(..., max_length=4000)


class OrchestrationRequest(BaseModel):
    """One farmer question, or one dashboard refresh.

    Everything except the intent is optional: the planner decides what can run
    with what was supplied and reports the rest as skipped, so a thin client
    can send very little and still get a useful answer.
    """
    model_config = ConfigDict(extra="forbid")

    request_id: Optional[str] = Field(
        None, description="Supply your own for correlation, or one is generated.")
    farm_id: Optional[str] = Field(None, min_length=1, max_length=64)
    history: List["HistoryTurn"] = Field(
        default_factory=list, max_length=12,
        description="Recent turns, oldest first, so the answer can refer back. "
                    "Sent by the Node backend, which owns the conversation.")

    intents: List[Intent] = Field(default_factory=list)
    capabilities: List[Capability] = Field(default_factory=list)
    agents: List[str] = Field(
        default_factory=list,
        description="Explicit agent names. Unknown names are ignored, never executed.")

    query: Optional[str] = Field(None, max_length=2000,
                                 description="The farmer's own words, any language.")
    language: str = Field("en", max_length=12)

    location: Optional[LocationInput] = None
    soil: Optional[Dict[str, Any]] = None
    crop: Optional[Dict[str, Any]] = None
    resources: Optional[Dict[str, Any]] = None
    market: Optional[Dict[str, Any]] = None

    explain: bool = Field(
        False, description="Add a farmer-readable answer written by the language model.")
    mode: str = Field(
        "text", pattern="^(text|voice)$",
        description="voice: a short answer written to be read aloud by text-to-speech.")

    @field_validator("agents")
    @classmethod
    def _sane_agent_names(cls, value: List[str]) -> List[str]:
        # Length and character bounds only; membership is checked against the
        # registry, which is what stops an arbitrary name from executing.
        for name in value:
            if not name or len(name) > 64 or not name.replace("_", "").isalnum():
                raise ValueError(f"Invalid agent name: {name!r}")
        return value

    @model_validator(mode="after")
    def _something_to_do(self) -> "OrchestrationRequest":
        if not (self.intents or self.capabilities or self.agents or self.query):
            raise ValueError(
                "Say what you need: an intent, a capability, an agent, or a question.")
        return self


# ── response ────────────────────────────────────────────────────────────────

class AgentResultOut(BaseModel):
    name: str
    version: str
    status: AgentStatus
    duration_ms: float
    attempts: int
    execution_id: str
    result: Optional[Any] = None
    confidence: Optional[float] = None
    data_age_seconds: Optional[float] = Field(
        None, description="Age of the underlying data. Null means unknown, never assumed fresh.")
    sources: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    error_code: Optional[ErrorCode] = None
    error: Optional[str] = None
    caused_by: Optional[str] = Field(
        None, description="The agent whose failure prevented this one from running.")
    finished_at: datetime


class SkippedOut(BaseModel):
    name: str
    reason: str
    missing: List[str] = Field(default_factory=list)
    caused_by: Optional[str] = None


class ConflictOut(BaseModel):
    topic: str
    description: str
    positions: Dict[str, str]
    resolution: str
    chosen: Optional[str] = None
    rationale: str = ""
    farmer_note: str = ""
    agents: List[str] = Field(default_factory=list)


class ProvenanceOut(BaseModel):
    """Which agents stand behind one part of the answer."""
    topic: str
    agents: List[str]
    produced_at: Optional[datetime] = None
    confidence: Optional[float] = None


class ExecutionOut(BaseModel):
    started_at: datetime
    duration_ms: float
    levels: List[List[str]] = Field(default_factory=list,
                                    description="Execution order; each inner list ran concurrently.")
    agents_run: int = 0
    agents_succeeded: int = 0
    agents_failed: int = 0
    agents_skipped: int = 0


class UnderstandingOut(BaseModel):
    """How the question was read. `query_en` is for search and logs, never shown."""
    intent: Optional[str] = None
    crop: Optional[str] = None
    language: str = "en"
    script: str = Field("latn", description="ISO 15924: latn, deva, gujr, taml, ...")
    query_en: Optional[str] = None
    confidence: Optional[float] = None
    source: str = Field("detected", description="model | detected")
    tier: str = Field("strong", description="How well the model handles this language.")


class ModelUsageOut(BaseModel):
    model: str
    purpose: str = Field(..., description="chat | embedding | transcription | speech")
    calls: int
    prompt_tokens: int
    completion_tokens: int
    estimated: bool
    audio_seconds: float = 0.0
    characters: int = 0


class UsageOut(BaseModel):
    """Tokens spent answering this request, across every model call.

    From the provider's own counts (what is billed); `estimated` is true when
    any call had to be counted locally because the provider did not say.
    """
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    calls: int = 0
    estimated: bool = False
    audio_seconds: float = 0.0
    characters: int = 0
    by_model: List[ModelUsageOut] = Field(default_factory=list)


class OrchestrationResponse(BaseModel):
    request_id: str
    status: OrchestrationStatus
    summary: str
    answer: Optional[str] = Field(
        None, description="The farmer-readable answer, when one was requested and available.")
    understanding: UnderstandingOut = Field(default_factory=UnderstandingOut)

    results: Dict[str, Any] = Field(
        default_factory=dict,
        description="Successful agent output, keyed by agent name. Absent means it did not run.")
    agent_results: List[AgentResultOut] = Field(default_factory=list)
    failed: List[str] = Field(default_factory=list)
    skipped: List[SkippedOut] = Field(default_factory=list)
    conflicts: List[ConflictOut] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    provenance: List[ProvenanceOut] = Field(default_factory=list)
    confidence: Optional[float] = Field(
        None, description="Lowest confidence among contributing agents, when they report it.")
    execution: ExecutionOut
    usage: UsageOut = Field(default_factory=UsageOut)


class ValidationErrorResponse(BaseModel):
    request_id: str
    status: OrchestrationStatus = OrchestrationStatus.VALIDATION_ERROR
    error_code: ErrorCode = ErrorCode.VALIDATION_FAILED
    message: str
    problems: List[str] = Field(default_factory=list)
