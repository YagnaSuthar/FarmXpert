"""
RetrievalAgent — answers knowledge questions from FarmXpert's own knowledge.

  RetrievalAgent().run(payload)  -> dict matching RetrievalResult
  RetrievalAgent()(state)        -> LangGraph node; never raises

It returns evidence, not prose: passages with their sources and a record of
how they were found. Turning that into a farmer's answer is the orchestrator's
explaining step, which is what keeps a retrieval miss from becoming a
confidently wrong reply.

Domain logic lives in RetrievalService; this class owns only input shaping.
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import ValidationError

from AI_Backend.agents.retrieval_agent.config import AGENT_ID, AGENT_VERSION
from AI_Backend.agents.retrieval_agent.schemas import RetrievalRequest, RetrievalResult
from AI_Backend.agents.retrieval_agent.service import RetrievalService

logger = logging.getLogger("farmxpert.retrieval")


class RetrievalAgent:
    AGENT_ID = AGENT_ID
    AGENT_VERSION = AGENT_VERSION

    def __init__(self) -> None:
        self.service = RetrievalService()

    async def __call__(self, state: Any) -> dict:
        """LangGraph node. A state with no question is not an error here -
        most farm requests are not knowledge questions - so it returns no
        update rather than failing the graph."""
        try:
            return {"knowledge": await self.run(state)}
        except (ValidationError, TypeError, ValueError) as exc:
            logger.info("Retrieval skipped - no usable question: %s", exc)
            return {}

    async def run(self, payload: Any) -> dict:
        """Retrieve. Returns a JSON-safe dict matching RetrievalResult."""
        return (await self.retrieve(payload)).model_dump(mode="json")

    async def retrieve(self, payload: Any) -> RetrievalResult:
        """Same as run(), but returns the typed result."""
        request = payload if isinstance(payload, RetrievalRequest) \
            else RetrievalRequest.model_validate(_normalise(payload))
        return await self.service.retrieve(request)

    def health(self) -> dict:
        """What the agent can reach right now, for a readiness probe."""
        from AI_Backend.agents.retrieval_agent.okf import get_bundle
        from AI_Backend.orchestration import llm

        bundle = get_bundle()
        return {
            "agent": AGENT_ID,
            "version": AGENT_VERSION,
            "curated_documents": len(bundle),
            "curated_directory": str(bundle.directory),
            "embeddings": "configured" if llm.available() else "not configured",
        }


def _normalise(payload: Any) -> dict:
    """Accept a question string, a request dict, or orchestrator state."""
    if isinstance(payload, str):
        return {"question": payload}
    if hasattr(payload, "model_dump"):
        payload = payload.model_dump(mode="json")
    if not isinstance(payload, dict):
        raise TypeError("Retrieval input must be a question, a mapping, or a request.")

    question = (payload.get("question") or payload.get("query")
                or payload.get("farmer_query") or "")
    crop = payload.get("crop")
    if isinstance(crop, dict):
        crop = crop.get("name")

    out: dict = {"question": question}
    if crop:
        out["crop"] = str(crop).strip().lower()
    for key in ("max_passages", "allow_discovery"):
        if payload.get(key) is not None:
            out[key] = payload[key]
    return out
