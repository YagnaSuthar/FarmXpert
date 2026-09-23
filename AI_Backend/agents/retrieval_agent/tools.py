"""
Retrieval Agent — Tools
========================
The individual capabilities the agent composes: read the curated map, fetch a
curated document, search the index, rewrite a query.

Each is a plain async function with a narrow contract and no shared state, so
each can be tested alone, called from a LangGraph node, or exposed over MCP
without carrying the rest of the agent with it. The decision of WHICH tool to
use, and when to stop, belongs to the service - not here.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Sequence

from AI_Backend.agents.retrieval_agent.config import (
    EMBED_MODEL,
    MAX_PASSAGES,
    MIN_SIMILARITY,
    OKF_EXCERPT_CHARS,
    OKF_MAX_DOCUMENTS,
)
from AI_Backend.agents.retrieval_agent.schemas import Passage, Source

logger = logging.getLogger("farmxpert.retrieval")


# ── curated layer ───────────────────────────────────────────────────────────

def okf_map(crop: Optional[str] = None) -> List[dict]:
    """The index of curated knowledge: id, title, summary, tags.

    Cheap by design. An agent reads this to learn what exists before deciding
    whether it needs to search anything.
    """
    from AI_Backend.agents.retrieval_agent.okf import get_bundle
    return get_bundle().map(crop=crop)


def okf_document(doc_id: str) -> Optional[Passage]:
    """One curated document by id. Deterministic: no ranking, no similarity."""
    from AI_Backend.agents.retrieval_agent.okf import get_bundle

    document = get_bundle().get(doc_id)
    if document is None:
        return None
    return Passage(title=document.title, text=document.text[:OKF_EXCERPT_CHARS],
                   source=Source.OKF, doc_id=document.id,
                   authority=document.entry.authority)


def okf_select(question: str, crop: Optional[str] = None,
               limit: int = OKF_MAX_DOCUMENTS) -> List[Passage]:
    """Curated documents whose metadata best covers the question.

    Term overlap against the map, not embeddings: the curated layer is meant
    to be predictable and free. Anything needing fuzzy matching is the
    discovery layer's job.
    """
    from AI_Backend.agents.retrieval_agent.okf import get_bundle

    return [Passage(title=doc.title, text=doc.text[:OKF_EXCERPT_CHARS],
                    source=Source.OKF, doc_id=doc.id,
                    authority=doc.entry.authority)
            for doc in get_bundle().select(question, crop=crop, limit=limit)]


# ── discovery layer ─────────────────────────────────────────────────────────

async def index_available() -> bool:
    """Is vector search usable right now? Never raises."""
    from AI_Backend.agents.retrieval_agent import store
    try:
        return await store.available()
    except Exception as exc:  # noqa: BLE001 - availability is a hint, not a failure
        logger.debug("Vector store unavailable: %s", exc)
        return False


async def vector_search(question: str, crop: Optional[str] = None,
                        limit: int = MAX_PASSAGES) -> List[Passage]:
    """Nearest passages from the index, above the similarity floor."""
    from AI_Backend.agents.retrieval_agent import store
    from AI_Backend.orchestration import llm

    vectors = await llm.embed([question], model=EMBED_MODEL, input_type="query")
    chunks = await store.search(vectors[0], limit=limit, crop=crop,
                                min_similarity=MIN_SIMILARITY)
    return [Passage(title=chunk.title, text=chunk.text, source=Source.INDEX,
                    doc_id=chunk.doc_id, similarity=chunk.score)
            for chunk in chunks]


async def vector_search_multi(questions: Sequence[str], crop: Optional[str] = None,
                              limit: int = MAX_PASSAGES) -> List[Passage]:
    """Search with several phrasings of one question, merged by rank.

    Used with the farmer's own words plus the English rendering from the
    understanding step: a multilingual embedding matches the original, the
    English one matches English-written handbook text, and either one alone
    misses cases the other finds. One embedding call for all phrasings; the
    searches run concurrently, so this costs no more time than one search.
    """
    import asyncio

    from AI_Backend.agents.retrieval_agent import store
    from AI_Backend.orchestration import llm

    phrasings = list(dict.fromkeys(q.strip() for q in questions if q and q.strip()))
    if not phrasings:
        return []
    vectors = await llm.embed(phrasings, model=EMBED_MODEL, input_type="query")
    batches = await asyncio.gather(*(
        store.search(vector, limit=limit, crop=crop, min_similarity=MIN_SIMILARITY)
        for vector in vectors))
    ranked = [[Passage(title=c.title, text=c.text, source=Source.INDEX,
                       doc_id=c.doc_id, similarity=c.score) for c in chunks]
              for chunks in batches]
    return rrf_merge(ranked)[:limit]


def rrf_merge(result_lists: Sequence[Sequence[Passage]], k: int = 60) -> List[Passage]:
    """Reciprocal rank fusion: a passage ranked well by any list rises.

    Rank-based, so similarities from different phrasings need not be on the
    same scale. Each passage keeps its best similarity, which is what the
    confidence and the similarity floor are judged on.
    """
    scores: Dict[str, float] = {}
    best: Dict[str, Passage] = {}
    for results in result_lists:
        for rank, passage in enumerate(results):
            key = f"{passage.doc_id}\x00{passage.text[:200]}"
            scores[key] = scores.get(key, 0.0) + 1.0 / (k + rank + 1)
            kept = best.get(key)
            if kept is None or (passage.similarity or 0) > (kept.similarity or 0):
                best[key] = passage
    return [best[key] for key in sorted(scores, key=lambda key: -scores[key])]


async def rewrite_query(question: str, crop: Optional[str] = None) -> Optional[str]:
    """A farmer's wording as a handbook would phrase it. One attempt, or None.

    Returns None whenever the model is unavailable or unhelpful; the caller
    then keeps the original results rather than waiting on a second search.
    """
    from AI_Backend.orchestration import llm

    if not llm.available():
        return None
    system = _prompt("query")
    try:
        rewritten = await llm.complete(
            system, f"Crop: {crop or 'unspecified'}\nQuestion: {question}",
            purpose="understand", temperature=0.0, max_tokens=40)
    except llm.LLMUnavailable:
        return None
    cleaned = rewritten.strip().strip('"').strip()
    return cleaned or None


# ── prompts ─────────────────────────────────────────────────────────────────

_PROMPT_CACHE: Dict[str, str] = {}


def _prompt(name: str) -> str:
    """Load a prompt from prompts/<name>.txt, cached.

    Prompts live in files so they can be edited and reviewed without touching
    Python, which is what makes them easy to tune.
    """
    if name in _PROMPT_CACHE:
        return _PROMPT_CACHE[name]
    import pathlib
    path = pathlib.Path(__file__).resolve().parent / "prompts" / f"{name}.txt"
    try:
        text = path.read_text(encoding="utf-8").strip()
    except OSError:
        logger.warning("Prompt %s missing at %s; using a built-in fallback.", name, path)
        text = _FALLBACK_PROMPTS.get(name, "")
    _PROMPT_CACHE[name] = text
    return text


_FALLBACK_PROMPTS = {
    "query": ("Rewrite the farmer's question as a short search query using the terms an "
              "agricultural handbook would use. Reply with the query only, at most 12 words."),
}


def dedupe(passages: Sequence[Passage]) -> List[Passage]:
    """Drop repeats, keeping the first (curated) copy of a document."""
    seen: set = set()
    out: List[Passage] = []
    for passage in passages:
        key = (passage.doc_id, passage.text[:120])
        if key in seen:
            continue
        seen.add(key)
        out.append(passage)
    return out
