"""
Vector store (pgvector)
========================
Reads and writes the `knowledge_chunks` table for the retrieval agent.

The table is created by the Node backend's migrations (it owns the schema);
this module reads it for search and rebuilds its rows on reindex. An earlier version issued
`CREATE TABLE IF NOT EXISTS` from the request path, which meant DDL ran with
the application's privileges, the schema was invisible to review, and a
mistyped vector dimension was discovered by a farmer rather than by a deploy.

Design notes:

* A short-lived session per call, from this service's own small pool. Concurrent
  agents therefore never share a session, which is the rule that keeps
  SQLAlchemy's async sessions safe.
* Every query is parameterised. The embedding is bound and cast, never
  interpolated into SQL text.
* Without a database or an embedding key the store reports itself unavailable
  and the retrieval agent falls back to the curated OKF layer alone.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from typing import List, Optional, Sequence

logger = logging.getLogger("farmxpert.retrieval.store")

from AI_Backend.agents.retrieval_agent.config import EMBED_DIM, EMBED_MODEL, VECTOR_TABLE as TABLE


@dataclass
class Chunk:
    """One retrievable passage."""
    chunk_id: str
    doc_id: str
    title: str
    text: str
    source: str = "okf"
    crops: Sequence[str] = ()
    score: Optional[float] = None        # cosine similarity, set by search


def _session_factory():
    """This service's own small pool - the knowledge index is the one table
    the AI backend reads directly (see AI_Backend/core/database.py)."""
    from AI_Backend.core import database
    return database.session


async def available() -> bool:
    """Is the store usable right now?

    Checks configuration and that the table exists. A missing table means the
    migration has not been run; that is a deployment state to report, not an
    error to raise at a farmer.
    """
    from AI_Backend.core import database
    if not database.configured():
        return False
    try:
        from AI_Backend.orchestration import llm
        if not llm.available():
            return False          # no embeddings, so no search is possible
    except ImportError:  # pragma: no cover
        return False

    from sqlalchemy import text as sql

    try:
        factory = _session_factory()
        async with factory() as session:
            found = await session.execute(
                sql("SELECT to_regclass(:name) IS NOT NULL"), {"name": TABLE})
            return bool(found.scalar())
    except Exception as exc:  # noqa: BLE001 - knowledge is optional infrastructure
        logger.warning("Knowledge store unavailable: %s: %s", type(exc).__name__, exc)
        return False


async def upsert(chunks: Sequence[Chunk], embeddings: Sequence[Sequence[float]], *,
                 embed_model: str = EMBED_MODEL) -> int:
    """Insert or replace chunks. Returns how many were written.

    Idempotent on `chunk_id`, so re-indexing the bundle updates passages in
    place rather than growing a second copy of the corpus.
    """
    from sqlalchemy import text as sql

    if len(chunks) != len(embeddings):
        raise ValueError("Each chunk needs exactly one embedding.")
    if not chunks:
        return 0

    for vector in embeddings:
        if len(vector) != EMBED_DIM:
            raise ValueError(
                f"Embedding has {len(vector)} dimensions, but the column holds "
                f"{EMBED_DIM}. The embedding model and the schema must match.")

    factory = _session_factory()
    written = 0
    async with factory() as session:
        for chunk, vector in zip(chunks, embeddings):
            await session.execute(sql(f"""
                INSERT INTO {TABLE}
                    (chunk_id, doc_id, title, text, source, crops, embedding, embed_model,
                     indexed_at, created_at, updated_at)
                VALUES
                    (:chunk_id, :doc_id, :title, :text, :source,
                     CAST(:crops AS jsonb), CAST(:embedding AS vector), :embed_model,
                     now(), now(), now())
                ON CONFLICT (chunk_id) DO UPDATE SET
                    doc_id = EXCLUDED.doc_id, title = EXCLUDED.title,
                    text = EXCLUDED.text, source = EXCLUDED.source,
                    crops = EXCLUDED.crops, embedding = EXCLUDED.embedding,
                    embed_model = EXCLUDED.embed_model,
                    indexed_at = now(), updated_at = now()"""),
                {"chunk_id": chunk.chunk_id, "doc_id": chunk.doc_id,
                 "title": chunk.title, "text": chunk.text, "source": chunk.source,
                 "crops": json.dumps([c.lower() for c in chunk.crops]),
                 "embedding": _vector_literal(vector), "embed_model": embed_model})
            written += 1
        await session.commit()
    logger.info("Knowledge store updated | chunks=%d", written)
    return written


async def search(embedding: Sequence[float], *, limit: int = 5,
                 crop: Optional[str] = None,
                 min_similarity: float = 0.25,
                 embed_model: str = EMBED_MODEL) -> List[Chunk]:
    """Nearest chunks by cosine similarity.

    `min_similarity` exists so a question the corpus does not cover returns
    nothing rather than the least-bad passage in the index - the classic RAG
    failure, which reads as confident and is wrong.
    """
    from sqlalchemy import text as sql

    factory = _session_factory()
    # Only vectors from the model that embedded the question are comparable.
    filters = " WHERE embed_model = :embed_model"
    params = {"embedding": _vector_literal(embedding), "limit": int(limit),
              "embed_model": embed_model}
    if crop:
        # Passages tagged with no crop are general and always eligible.
        filters += " AND (crops @> CAST(:crop AS jsonb) OR crops = '[]'::jsonb)"
        params["crop"] = json.dumps([crop.strip().lower()])

    async with factory() as session:
        rows = (await session.execute(sql(f"""
            SELECT chunk_id, doc_id, title, text, source, crops,
                   1 - (embedding <=> CAST(:embedding AS vector)) AS similarity
            FROM {TABLE}{filters}
            ORDER BY embedding <=> CAST(:embedding AS vector)
            LIMIT :limit"""), params)).all()

    out: List[Chunk] = []
    for row in rows:
        similarity = float(row.similarity)
        if similarity < min_similarity:
            continue
        crops = row.crops if isinstance(row.crops, list) else json.loads(row.crops or "[]")
        out.append(Chunk(chunk_id=row.chunk_id, doc_id=row.doc_id, title=row.title,
                         text=row.text, source=row.source, crops=tuple(crops),
                         score=round(similarity, 4)))
    return out


async def count() -> int:
    from sqlalchemy import text as sql
    factory = _session_factory()
    async with factory() as session:
        result = await session.execute(sql(f"SELECT count(*) FROM {TABLE}"))
        return int(result.scalar() or 0)


async def prune(keep_chunk_ids: Sequence[str]) -> int:
    """Delete chunks that are no longer in the bundle.

    Re-indexing updates what still exists but cannot know what was removed.
    Without this, a passage deleted from the handbook keeps being retrieved
    and quoted to farmers long after it was withdrawn.
    """
    from sqlalchemy import text as sql

    if not keep_chunk_ids:
        return 0
    factory = _session_factory()
    async with factory() as session:
        result = await session.execute(
            sql(f"DELETE FROM {TABLE} WHERE NOT (chunk_id = ANY(:keep))"),
            {"keep": list(keep_chunk_ids)})
        await session.commit()
    removed = result.rowcount or 0
    if removed:
        logger.info("Knowledge store pruned | removed=%d", removed)
    return removed


def _vector_literal(vector: Sequence[float]) -> str:
    """pgvector's text form. Bound as a parameter, then cast in SQL."""
    return "[" + ",".join(f"{float(v):.6f}" for v in vector) + "]"


def chunk_id_for(doc_id: str, index: int, text: str) -> str:
    """Stable id, so re-indexing updates a chunk instead of duplicating it."""
    digest = hashlib.sha1(f"{doc_id}:{index}:{text}".encode("utf-8")).hexdigest()[:16]
    return f"{doc_id}#{index}-{digest}"
