"""
Orchestration service
======================
One entry point, and stateless: the Node backend sends the full context and
stores the result. This service owns the sequence and nothing else:

    understand -> build context -> plan -> execute -> detect conflicts
              -> aggregate -> explain

Everything up to "explain" is `_prepare`; the two public paths differ only in
how the answer is written:

    run()           blocking: one JSON response
    stream()        yields ("meta" | "delta" | "done", payload) events so the
                    farmer sees the answer while it is written
    stream_voice()  speech in, speech out: transcript, the same events, and one
                    audio clip per sentence as soon as it is spoken

Each step lives in its own module, so this file stays readable and none of the
steps know about each other. The router translates results into HTTP; no
orchestration logic lives in the route.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Dict, List, Optional, Tuple

from AI_Backend.orchestration import aggregate, conflicts as conflict_rules, llm, usage
from AI_Backend.orchestration.contracts import (
    ExecutionContext,
    OrchestrationStatus,
    Timer,
)
from AI_Backend.orchestration.engine import ExecutionEngine
from AI_Backend.orchestration.observability import Event, emit
from AI_Backend.orchestration.planner import Intent, Planner
from AI_Backend.orchestration.registry import REGISTRY, AgentRegistry
from AI_Backend.orchestration.schemas import (
    OrchestrationRequest,
    OrchestrationResponse,
    UnderstandingOut,
    UsageOut,
)

logger = logging.getLogger("farmxpert.orchestration")


@dataclass
class _Prepared:
    """Everything known before the answer is written."""
    request: OrchestrationRequest
    request_id: str
    started_at: datetime
    timer: Timer
    understanding: Dict[str, Any]
    plan: Any = None
    results: Dict[str, Any] = field(default_factory=dict)
    found: List[Any] = field(default_factory=list)
    status: Optional[OrchestrationStatus] = None
    outputs: Dict[str, Any] = field(default_factory=dict)
    skipped: List[Any] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    empty: Optional[OrchestrationResponse] = None   # nothing could run

    @property
    def wants_answer(self) -> bool:
        return bool(self.request.explain and self.outputs
                    and self.status != OrchestrationStatus.FAILED)

    def answer_args(self) -> Tuple[tuple, Dict[str, Any]]:
        return ((self.request.query, self.outputs),
                dict(language=self.understanding["language"],
                     script=self.understanding["script"],
                     mode=self.request.mode,
                     conflicts=[c.__dict__ for c in self.found],
                     warnings=self.warnings,
                     history=[turn.model_dump() for turn in self.request.history]))


class OrchestratorService:
    """Coordinates agents. Contains no farming logic of its own."""

    def __init__(self,
                 registry: AgentRegistry = REGISTRY,
                 engine: Optional[ExecutionEngine] = None) -> None:
        self.registry = registry
        self.planner = Planner(registry)
        self.engine = engine or ExecutionEngine()

    # ── public paths ────────────────────────────────────────────────────

    async def run(self, request: OrchestrationRequest) -> OrchestrationResponse:
        # Every model call made while answering - understanding, agents,
        # retrieval, the written answer - is metered onto this request.
        meter, token = usage.start()
        try:
            prepared = await self._prepare(request)
            if prepared.empty is not None:
                response = prepared.empty
            else:
                answer = None
                if prepared.wants_answer:
                    args, kwargs = prepared.answer_args()
                    answer = await llm.answer(*args, **kwargs)
                response = self._finish(prepared, answer)
        finally:
            usage.stop(token)
        response.usage = UsageOut(**meter.summary())
        return response

    async def stream(self, request: OrchestrationRequest) -> AsyncIterator[Tuple[str, Any]]:
        """The same run, as events. The last event is always "done".

        meta   {request_id, understanding, status, agents}  once the agents are done
        delta  {"text": "..."}                              pieces of the answer
        done   the full OrchestrationResponse, as JSON
        """
        meter, token = usage.start()
        try:
            async for name, payload in self._stream_core(request):
                if name == "final":
                    response = payload
                else:
                    yield name, payload
        finally:
            usage.stop(token)
        response.usage = UsageOut(**meter.summary())
        yield "done", response.model_dump(mode="json")

    async def stream_voice(self, audio: bytes, mime: str, request: OrchestrationRequest,
                           audio_seconds: Optional[float] = None
                           ) -> AsyncIterator[Tuple[str, Any]]:
        """Speech in, speech out: transcribe -> the streamed run -> speak each sentence.

        transcript  {text, language}             as soon as speech-to-text is done
        meta/delta  as stream()
        audio       {seq, format, text, data}    base64 audio, one per sentence, in order
        done        full response + transcript; usage includes speech both ways
        """
        from AI_Backend.orchestration import speech

        meter, token = usage.start()
        speaker = speech.SentenceSpeaker(language_hint=request.language)
        try:
            transcript = await speech.transcribe(audio, mime, request.language,
                                                 audio_seconds=audio_seconds)
            yield "transcript", {"text": transcript, "language": request.language}
            voiced = request.model_copy(update={"query": transcript, "mode": "voice",
                                                "explain": True})
            async for name, payload in self._stream_core(voiced):
                if name == "final":
                    response = payload
                    continue
                if name == "meta":
                    speaker.language = payload["understanding"]["language"]
                yield name, payload
                if name == "delta":
                    speaker.feed(payload["text"])
                    for ready in speaker.ready():
                        yield "audio", ready
            speaker.close()
            async for ready in speaker.drain():
                yield "audio", ready
        finally:
            # A farmer who hangs up must not keep paying for speech.
            speaker.cancel()
            usage.stop(token)
        response.usage = UsageOut(**meter.summary())
        body = response.model_dump(mode="json")
        body["transcript"] = transcript
        yield "done", body

    async def _stream_core(self, request: OrchestrationRequest) -> AsyncIterator[Tuple[str, Any]]:
        """meta and delta events, then ("final", OrchestrationResponse) without usage."""
        prepared = await self._prepare(request)
        if prepared.empty is not None:
            yield "final", prepared.empty
            return
        yield "meta", {
            "request_id": prepared.request_id,
            "understanding": prepared.understanding,
            "status": prepared.status.value if prepared.status else None,
            "agents": sorted(prepared.outputs),
        }
        parts: List[str] = []
        if prepared.wants_answer:
            args, kwargs = prepared.answer_args()
            async for piece in llm.answer_stream(*args, **kwargs):
                parts.append(piece)
                yield "delta", {"text": piece}
        yield "final", self._finish(prepared, "".join(parts).strip() or None)

    # ── steps ───────────────────────────────────────────────────────────

    async def _prepare(self, request: OrchestrationRequest) -> _Prepared:
        request_id = request.request_id or uuid.uuid4().hex
        timer = Timer()
        started_at = datetime.now(timezone.utc)

        emit(Event.ORCHESTRATION_STARTED, request_id,
             farm_id=request.farm_id,
             intents=[i.value for i in request.intents],
             explicit_agents=list(request.agents),
             has_query=bool(request.query))

        intents, understanding = await self._understand(request)
        prepared = _Prepared(request=request, request_id=request_id, started_at=started_at,
                             timer=timer, understanding=understanding)
        context = self._context(request, request_id, understanding)

        plan = self.planner.plan(context,
                                 intents=intents,
                                 capabilities=request.capabilities,
                                 agent_names=request.agents)
        prepared.plan = plan
        emit(Event.AGENT_SELECTED, request_id,
             selected=plan.selected_names,
             levels=plan.describe(),
             skipped=[s.name for s in plan.skipped])

        if plan.is_empty:
            prepared.empty = self._nothing_to_run(request_id, plan, started_at, timer,
                                                  understanding)
            return prepared

        results = await self.engine.run(plan, context)
        found = conflict_rules.detect(context)
        for conflict in found:
            emit(Event.AGENT_CONFLICT_DETECTED, request_id,
                 topic=conflict.topic, agents=conflict.agents,
                 resolution=conflict.resolution.value)

        specs = {spec.name: spec for level in plan.levels for spec in level}
        prepared.results = results
        prepared.found = found
        prepared.status = aggregate.overall_status(results, specs)
        prepared.outputs = aggregate.successful_outputs(results)
        prepared.skipped = aggregate.to_skipped(plan.skipped, results)
        prepared.warnings = aggregate.warnings_for(results, specs)
        return prepared

    def _finish(self, p: _Prepared, answer: Optional[str]) -> OrchestrationResponse:
        response = OrchestrationResponse(
            request_id=p.request_id,
            status=p.status,
            summary=aggregate.summarise(p.status, p.results, p.skipped, p.found),
            answer=answer,
            understanding=UnderstandingOut(**p.understanding),
            results=p.outputs,
            agent_results=aggregate.to_agent_results(p.results),
            failed=aggregate.failed_agents(p.results),
            skipped=p.skipped,
            conflicts=aggregate.to_conflicts(p.found),
            warnings=p.warnings,
            provenance=aggregate.provenance(p.results),
            confidence=aggregate.overall_confidence(p.results),
            execution=aggregate.execution_summary(p.plan, p.results, p.started_at, p.timer.ms))

        emit(_completion_event(p.status), p.request_id,
             status=p.status.value,
             duration_ms=round(p.timer.ms, 1),
             succeeded=response.execution.agents_succeeded,
             failed=response.execution.agents_failed,
             skipped=response.execution.agents_skipped,
             conflicts=len(p.found),
             language=p.understanding["language"])
        return response

    async def _understand(self, request: OrchestrationRequest):
        """Work out what is being asked, and in which language and script.

        The model only proposes an intent: whatever it returns is a member of
        the closed Intent set or is discarded; it never names an agent, so
        there is no path from model output to execution. Language and script
        are detected deterministically even when intents are given and the
        model is not called.
        """
        from AI_Backend.orchestration import languages

        intents: List[Intent] = list(request.intents)
        text = request.query or ""
        if not intents and not request.capabilities and not request.agents and text:
            understood = await llm.understand(text, hint_language=request.language)
            intents = [understood["intent"]]
        else:
            detected = languages.detect(text, request.language) if text else None
            code = detected.language if detected else (
                languages.normalise_code(request.language) or "en")
            understood = {
                "intent": intents[0] if intents else None, "crop": None,
                "language": code,
                "script": detected.script if detected else languages.get(code).scripts[0],
                "query_en": text if code == "en" and text else None,
                "confidence": None, "source": "detected",
                "tier": languages.get(code).tier,
            }
        understood["intent"] = understood["intent"].value if isinstance(
            understood.get("intent"), Intent) else understood.get("intent")
        return intents, understood

    def _context(self, request: OrchestrationRequest, request_id: str,
                 understanding: Dict[str, Any]) -> ExecutionContext:
        """Assemble what agents may read.

        Everything comes from the request. The Node backend owns the database:
        it resolves the farm's location, latest soil reading and field before
        calling here, so this service never queries a database on the path of
        a farmer's question.
        """
        location = request.location.model_dump() if request.location else None
        soil: Optional[Dict[str, Any]] = dict(request.soil) if request.soil else None
        crop: Dict[str, Any] = dict(request.crop) if request.crop else {}

        if understanding.get("crop") and not crop.get("name"):
            crop["name"] = understanding["crop"]

        return ExecutionContext(
            request_id=request_id,
            farm_id=request.farm_id,
            farmer_query=request.query,
            language=understanding["language"],
            location=location,
            soil=soil,
            crop=crop or None,
            resources=dict(request.resources) if request.resources else None,
            market=dict(request.market) if request.market else None,
            # The English rendering lets English-indexed knowledge match a
            # question asked in any language.
            extras={"query_en": understanding.get("query_en"),
                    "script": understanding.get("script")})

    def _nothing_to_run(self, request_id: str, plan, started_at, timer,
                        understanding: Dict[str, Any]) -> OrchestrationResponse:
        """Nothing could run - say precisely what was missing.

        This is a real answer, not an error: the farmer is told which piece of
        information would unlock the request.
        """
        skipped = aggregate.to_skipped(plan.skipped, {})
        missing = sorted({item for s in skipped for item in s.missing})
        summary = ("No agent could run with the information provided."
                   + (f" Missing: {', '.join(missing)}." if missing else ""))
        emit(Event.ORCHESTRATION_VALIDATION_FAILED, request_id, missing=missing)
        return OrchestrationResponse(
            request_id=request_id,
            status=OrchestrationStatus.VALIDATION_ERROR,
            summary=summary,
            understanding=UnderstandingOut(**understanding),
            results={},
            skipped=skipped,
            warnings=[summary],
            execution=aggregate.execution_summary(plan, {}, started_at, timer.ms))


def _completion_event(status: OrchestrationStatus) -> Event:
    if status == OrchestrationStatus.SUCCESS:
        return Event.ORCHESTRATION_COMPLETED
    if status == OrchestrationStatus.PARTIAL_SUCCESS:
        return Event.ORCHESTRATION_PARTIAL_SUCCESS
    return Event.ORCHESTRATION_FAILED
