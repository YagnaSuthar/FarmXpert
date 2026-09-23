"""
Orchestrator API
=================
Thin by design: validate, correlate, delegate, translate errors. No
orchestration logic lives here.

Called by the Node backend, which owns the database and the conversation.
This service is stateless: it receives the farm's context, runs the agents,
and returns the result.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, Response, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import ValidationError

from AI_Backend.orchestration.agents import register_all
from AI_Backend.orchestration.contracts import OrchestrationStatus
from AI_Backend.orchestration.registry import REGISTRY, RegistryError
from AI_Backend.orchestration.schemas import (
    OrchestrationRequest,
    OrchestrationResponse,
    ValidationErrorResponse,
)
from AI_Backend.orchestration.service import OrchestratorService

router = APIRouter(prefix="/orchestrator", tags=["Orchestrator"])
logger = logging.getLogger(__name__)

register_all()
service = OrchestratorService()


@router.post(
    "/execute",
    response_model=OrchestrationResponse,
    summary="Run the agents needed to answer one farm request",
    description=(
        "Selects the agents required for the request, runs independent ones concurrently, "
        "passes results to dependent ones, and returns everything that succeeded along "
        "with an honest account of what did not. A partial answer is normal and is "
        "reported as `partial_success`; nothing missing is ever estimated or invented."
    ),
)
async def execute(request: OrchestrationRequest, response: Response) -> OrchestrationResponse:
    result = await service.run(request)
    # A request that could not run at all is a client problem, not a server
    # one, but it still carries a full body explaining what was missing.
    if result.status == OrchestrationStatus.VALIDATION_ERROR:
        response.status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    return result


@router.post(
    "/execute/stream",
    summary="The same run, streamed as server-sent events",
    description=(
        "Events: `meta` (how the question was read, once agents finish), `delta` "
        "(pieces of the written answer), `done` (the full response, exactly as "
        "`/execute` returns it). `error` replaces `done` only if the run itself fails."
    ),
    response_class=StreamingResponse,
)
async def execute_stream(request: OrchestrationRequest) -> StreamingResponse:
    async def events():
        try:
            async for name, payload in service.stream(request):
                yield sse(name, payload)
        except Exception:  # noqa: BLE001 - the stream must end with a clear event
            logger.exception("Streamed orchestration failed | request_id=%s", request.request_id)
            yield sse("error", {"code": "orchestration_failed",
                                "message": "The request could not be completed."})

    return StreamingResponse(events(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache, no-transform",
        # Proxies (nginx) must pass each event on at once, not buffer the stream.
        "X-Accel-Buffering": "no",
    })


@router.post(
    "/voice/stream",
    summary="Speech in, speech out, streamed as server-sent events",
    description=(
        "Multipart: `audio` (webm/ogg Opus, m4a, wav or mp3; at most VOICE_MAX_BYTES), "
        "`request` (the OrchestrationRequest as JSON, without `query`), optional "
        "`audio_seconds`. Events: `transcript`, then those of /execute/stream, plus "
        "`audio` (one base64 clip per sentence, in order). A speech failure ends the "
        "stream with `error` carrying a stable `code` (no_speech, audio_too_large, "
        "unsupported_audio, speech_unavailable)."
    ),
    response_class=StreamingResponse,
)
async def voice_stream(audio: UploadFile = File(...), request: str = Form(...),
                       audio_seconds: Optional[float] = Form(None)) -> StreamingResponse:
    from AI_Backend.orchestration import speech

    limit = int(os.getenv("VOICE_MAX_BYTES", str(2 * 1024 * 1024)))
    # Read one byte past the limit: enough to know it is too big, without
    # buffering an arbitrarily large upload.
    data = await audio.read(limit + 1)
    try:
        fields = json.loads(request)
        if not isinstance(fields, dict):
            raise ValueError("request must be a JSON object")
        # The question is the recording; the transcript replaces this.
        fields.setdefault("query", "(voice question)")
        parsed = OrchestrationRequest.model_validate(fields)
    except ValidationError as exc:   # before ValueError: it is a subclass
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail=exc.errors(include_url=False, include_input=False))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail=f"request is not valid JSON: {exc}") from None

    async def events():
        try:
            if len(data) > limit:
                raise speech.SpeechError("audio_too_large", "The recording is too long.")
            async for name, payload in service.stream_voice(
                    data, audio.content_type or "", parsed, audio_seconds=audio_seconds):
                yield sse(name, payload)
        except speech.SpeechError as exc:
            yield sse("error", {"code": exc.code, "message": str(exc)})
        except Exception:  # noqa: BLE001 - the stream must end with a clear event
            logger.exception("Voice orchestration failed | request_id=%s", parsed.request_id)
            yield sse("error", {"code": "orchestration_failed",
                                "message": "The request could not be completed."})

    return StreamingResponse(events(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"})


def sse(event: str, payload) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False, default=str)}\n\n"


@router.get("/agents", summary="The agent catalog")
async def agents() -> dict:
    """What can run, what each agent needs, and what it depends on."""
    return {"agents": REGISTRY.catalog(), "count": len(REGISTRY.all(include_disabled=True))}


@router.post("/agents/{name}/enabled", summary="Enable or disable one agent")
async def set_enabled(name: str, enabled: bool = True) -> dict:
    """Take an agent out of service without a deploy.

    A disabled agent is treated as absent: requests that needed it are skipped
    with a reason instead of failing. This is the lever for an upstream outage.
    """
    try:
        spec = REGISTRY.set_enabled(name, enabled)
    except RegistryError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    return {"name": spec.name, "enabled": spec.enabled}


@router.get("/health", summary="Liveness and catalog health")
async def health() -> dict:
    from AI_Backend.orchestration import llm
    return {
        "status": "ok",
        "agents_registered": len(REGISTRY.all(include_disabled=True)),
        "agents_enabled": len(REGISTRY.all()),
        "language_model": "configured" if llm.available() else "not configured",
    }


# ── knowledge layer ─────────────────────────────────────────────────────────

@router.get("/knowledge", summary="What the curated knowledge bundle holds")
async def knowledge() -> dict:
    """The OKF map: the cheap overview an agent reads before retrieving."""
    from AI_Backend.agents.retrieval_agent.okf import get_bundle

    bundle = get_bundle()
    return {"documents": len(bundle), "map": bundle.map()}


@router.post("/knowledge/reindex", summary="Rebuild the vector index from the bundle")
async def reindex() -> dict:
    """Embed the curated Markdown into pgvector for discovery search.

    Run on deploy or after editing the bundle - never during a farmer's
    request. Safe to repeat: chunk ids are stable, so this updates in place.
    """
    from AI_Backend.agents.retrieval_agent.indexer import reindex as run_reindex

    return await run_reindex()
