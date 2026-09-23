"""
Retrieval Agent — Service
==========================
The agentic loop, and the only place that decides how hard to look.

    1. read the curated map and address the documents that match
    2. stop if that is enough - most farmer questions are answered here, at
       no embedding cost and with fully predictable results
    3. otherwise search the index
    4. grade the results; if the best match is weak, rewrite the query once
       and search again, keeping whichever attempt was better
    5. return passages and a record of what was done

Step 4 happens at most once. An agent that keeps rewriting and re-searching
gets slightly better answers for unbounded cost, and on a farmer-facing path
the extra seconds cost more than the extra relevance is worth.

The service returns evidence and never writes prose. Nothing here fabricates:
when the knowledge base has nothing, it says so.
"""

from __future__ import annotations

import logging
from typing import List, Optional

from AI_Backend.agents.retrieval_agent import tools
from AI_Backend.agents.retrieval_agent.config import (
    GOOD_ENOUGH_SIMILARITY,
    MAX_REWRITES,
    OKF_ENOUGH_DOCUMENTS,
    OKF_MAX_DOCUMENTS,
)
from AI_Backend.agents.retrieval_agent.schemas import (
    Passage,
    RetrievalRequest,
    RetrievalResult,
    Source,
)

logger = logging.getLogger("farmxpert.retrieval")


class RetrievalService:
    """Stateless. Safe to instantiate per request."""

    async def retrieve(self, request: RetrievalRequest) -> RetrievalResult:
        result = RetrievalResult(question=request.question)
        passages: List[Passage] = []

        curated = self._curated(request, result)
        passages.extend(curated)

        if self._curated_is_enough(curated, request):
            result.retrieval_steps.append(
                "Curated knowledge covered the question; no index search was needed.")
            return self._finish(result, passages, request)

        if not request.allow_discovery:
            result.retrieval_steps.append("Index search was not permitted for this request.")
            return self._finish(result, passages, request)

        discovered = await self._discover(request, result)
        passages.extend(discovered)
        return self._finish(result, passages, request)

    # ── step 1: curated ─────────────────────────────────────────────────

    def _curated(self, request: RetrievalRequest, result: RetrievalResult) -> List[Passage]:
        try:
            # Curated metadata is English: match the farmer's words and the
            # English rendering, originals first.
            found = tools.okf_select(request.question, crop=request.crop,
                                     limit=OKF_MAX_DOCUMENTS)
            english = _english(request)
            if english:
                found = tools.dedupe(found + tools.okf_select(
                    english, crop=request.crop, limit=OKF_MAX_DOCUMENTS))[:OKF_MAX_DOCUMENTS]
        except Exception as exc:  # noqa: BLE001 - a bad bundle must not sink the answer
            logger.warning("Curated lookup failed: %s: %s", type(exc).__name__, exc)
            result.warnings.append("Curated knowledge could not be read.")
            return []

        total = len(tools.okf_map())
        result.retrieval_steps.append(
            f"Read the curated map ({total} documents); {len(found)} matched the question"
            + (f" for {request.crop}." if request.crop else "."))
        result.curated_hits = len(found)
        return found

    @staticmethod
    def _curated_is_enough(curated: List[Passage], request: RetrievalRequest) -> bool:
        """Whether to stop before spending an embedding call.

        Only when the curated layer produced its full quota. One weak match is
        not a reason to skip the index.
        """
        return len(curated) >= min(OKF_ENOUGH_DOCUMENTS, request.max_passages)

    # ── step 3-4: discovery ─────────────────────────────────────────────

    async def _discover(self, request: RetrievalRequest,
                        result: RetrievalResult) -> List[Passage]:
        if not await tools.index_available():
            result.retrieval_steps.append(
                "Index search unavailable (no vector store or embedding key configured).")
            return []

        english = _english(request)
        try:
            if english:
                found = await tools.vector_search_multi(
                    [request.question, english], crop=request.crop, limit=request.max_passages)
            else:
                found = await tools.vector_search(request.question, crop=request.crop,
                                                  limit=request.max_passages)
        except Exception as exc:  # noqa: BLE001 - discovery is the optional half
            logger.warning("Index search failed: %s: %s", type(exc).__name__, exc)
            result.warnings.append("Index search failed; curated knowledge only.")
            result.retrieval_steps.append("Index search failed.")
            return []

        result.searched_index = True
        best = max((p.similarity or 0.0 for p in found), default=0.0)
        result.retrieval_steps.append(
            f"Searched the index; {len(found)} passage(s) above the floor, "
            f"best similarity {best:.2f}.")

        # With an English rendering already searched, a rewrite would repeat it.
        if best < GOOD_ENOUGH_SIMILARITY and MAX_REWRITES and not english:
            found, best = await self._retry_once(request, result, found, best)

        result.indexed_hits = len(found)
        result.best_similarity = round(best, 4) if found else None
        return found

    async def _retry_once(self, request: RetrievalRequest, result: RetrievalResult,
                          found: List[Passage], best: float):
        """One rewrite, kept only if it actually did better."""
        rewritten = await tools.rewrite_query(request.question, crop=request.crop)
        if not rewritten or rewritten.lower() == request.question.lower():
            return found, best

        result.rewritten_query = rewritten
        result.retrieval_steps.append(
            f"Results were weak ({best:.2f}); retried as: {rewritten}")
        try:
            second = await tools.vector_search(rewritten, crop=request.crop,
                                               limit=request.max_passages)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Rewritten search failed: %s", type(exc).__name__)
            return found, best

        second_best = max((p.similarity or 0.0 for p in second), default=0.0)
        if second and second_best > best:
            result.retrieval_steps.append(
                f"The rewritten query was better ({second_best:.2f}); using it.")
            return second, second_best

        result.retrieval_steps.append("The rewrite did not improve on the original.")
        return found, best

    # ── step 5: finish ──────────────────────────────────────────────────

    @staticmethod
    def _finish(result: RetrievalResult, passages: List[Passage],
                request: RetrievalRequest) -> RetrievalResult:
        kept = tools.dedupe(passages)[:request.max_passages]
        result.passages = kept
        result.passage_count = len(kept)
        result.sources = sorted({f"{p.source.value}:{p.doc_id}" for p in kept})

        if not kept:
            # An honest empty answer. The orchestrator will say the knowledge
            # base has nothing on this, rather than inventing something.
            result.warnings.append("No knowledge was found for this question.")
        return result


def _english(request: RetrievalRequest) -> Optional[str]:
    """The English rendering, when it says something the original does not."""
    english = (request.question_en or "").strip()
    if not english or english.lower() == request.question.strip().lower():
        return None
    return english
