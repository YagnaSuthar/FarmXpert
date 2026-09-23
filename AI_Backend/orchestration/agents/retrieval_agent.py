"""
Adapter — Retrieval Agent
==========================
Registers `AI_Backend.agents.retrieval_agent` with the orchestrator.

The agent itself owns all the retrieval logic: the curated OKF layer, the
vector index, the grading and the single bounded rewrite. This file only
translates the execution context into the agent's request and validates what
comes back - exactly like every other adapter in this package.

That separation matters. Retrieval is a domain capability, so it lives with
the other agents and can be called directly, over MCP, or from a LangGraph
node without the orchestrator. Putting its logic here would have made the
orchestration layer the only way to use it.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, List

from AI_Backend.agents.retrieval_agent.agent import RetrievalAgent
from AI_Backend.agents.retrieval_agent.config import AGENT_VERSION, MAX_PASSAGES
from AI_Backend.orchestration.contracts import (
    AgentSpec,
    Capability,
    Criticality,
    ExecutionContext,
    NormalizedOutput,
    RetryPolicy,
)
from AI_Backend.orchestration.engine import AgentInputError, AgentOutputError


def build_retrieval() -> AgentSpec:
    agent = RetrievalAgent()

    async def execute(context: ExecutionContext) -> Any:
        question = (context.farmer_query or "").strip()
        if not question:
            raise AgentInputError("The retrieval agent needs a question.")
        return await agent.run({
            "question": question,
            "question_en": (context.extras or {}).get("query_en"),
            "crop": (context.crop or {}).get("name"),
            "max_passages": MAX_PASSAGES,
        })

    def validate_output(raw: Any) -> NormalizedOutput:
        if not isinstance(raw, dict) or "passages" not in raw:
            raise AgentOutputError("Retrieval returned an unexpected shape.")
        passages = raw["passages"]
        if not isinstance(passages, list):
            raise AgentOutputError("Retrieval passages were not a list.")
        if raw.get("passage_count") != len(passages):
            raise AgentOutputError("Retrieval passage count does not match its passages.")

        warnings: List[str] = list(raw.get("warnings") or [])

        # Curated documents are addressed, not matched, so they carry no
        # similarity. Treating "no score" as "no confidence" would understate
        # the layer that is actually the most reliable.
        similarities = [p.get("similarity") for p in passages
                        if isinstance(p, dict) and p.get("similarity") is not None]
        curated = [p for p in passages
                   if isinstance(p, dict) and p.get("source") == "okf"]
        if similarities:
            confidence = max(similarities)
        elif curated:
            confidence = 0.8
        else:
            confidence = None

        return NormalizedOutput(
            data=raw,
            confidence=confidence,
            produced_at=datetime.now(timezone.utc),
            sources=list(raw.get("sources") or []),
            warnings=warnings)

    return AgentSpec(
        name="retrieval_agent",
        version=AGENT_VERSION,
        description=("Answers knowledge questions from the curated FarmXpert handbook, "
                     "falling back to vector search over the indexed corpus."),
        capabilities=frozenset({Capability.KNOWLEDGE_ANSWER}),
        requires_context=frozenset({"farmer_query"}),
        optional_context=frozenset({"crop"}),
        criticality=Criticality.BEST_EFFORT,
        timeout_s=20.0,
        retry=RetryPolicy(max_attempts=2, base_delay_s=0.5),
        execute=execute,
        validate_output=validate_output,
        input_schema={"type": "object",
                      "properties": {"question": {"type": "string"},
                                     "crop": {"type": "string"}},
                      "required": ["question"]})
