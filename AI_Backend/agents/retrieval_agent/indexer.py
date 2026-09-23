"""
Indexer — OKF Markdown into retrievable chunks
===============================================
The bridge between the two knowledge layers. OKF files are clean, small and
well-headed, which makes them the best possible input to a chunker: the split
follows the author's own headings instead of guessing at boundaries.

Chunking rules:
  * split on Markdown headings, never mid-sentence;
  * a section longer than the budget splits on paragraphs;
  * every chunk carries its document title, so a retrieved passage is never
    stranded without context;
  * ids are stable, so re-indexing updates rather than duplicates.
"""

from __future__ import annotations

import logging
import re
from typing import Iterable, List, Sequence

from AI_Backend.agents.retrieval_agent.config import (
    EMBED_BATCH,
    EMBED_MODEL,
    MAX_CHUNK_CHARS,
    MIN_CHUNK_CHARS,
)
from AI_Backend.agents.retrieval_agent.okf import OKFDocument, get_bundle
from AI_Backend.agents.retrieval_agent.store import Chunk, chunk_id_for

logger = logging.getLogger("farmxpert.retrieval.indexer")



def chunk_document(document: OKFDocument) -> List[Chunk]:
    """Split one OKF document into retrievable passages."""
    chunks: List[Chunk] = []
    for index, (heading, body) in enumerate(_sections(document.text)):
        for part in _split_long(body):
            text = f"{document.title} — {heading}\n{part}".strip() if heading else \
                   f"{document.title}\n{part}".strip()
            if len(text) < MIN_CHUNK_CHARS:
                continue
            chunks.append(Chunk(
                chunk_id=chunk_id_for(document.id, len(chunks), text),
                doc_id=document.id,
                title=f"{document.title} — {heading}" if heading else document.title,
                text=text,
                source="okf",
                crops=tuple(c.lower() for c in document.entry.crops)))
    return chunks


def _sections(markdown: str):
    """(heading, body) pairs, following the author's headings."""
    lines = markdown.splitlines()
    heading = ""
    buffer: List[str] = []
    for line in lines:
        if re.match(r"^#{1,6}\s", line):
            if buffer:
                yield heading, "\n".join(buffer).strip()
                buffer = []
            heading = line.lstrip("# ").strip()
        else:
            buffer.append(line)
    if buffer:
        yield heading, "\n".join(buffer).strip()


def _split_long(body: str) -> List[str]:
    """Keep a long section readable without cutting a sentence in half."""
    body = body.strip()
    if len(body) <= MAX_CHUNK_CHARS:
        return [body] if body else []

    parts: List[str] = []
    current = ""
    for paragraph in re.split(r"\n\s*\n", body):
        if len(current) + len(paragraph) + 2 <= MAX_CHUNK_CHARS:
            current = f"{current}\n\n{paragraph}".strip()
        else:
            if current:
                parts.append(current)
            current = paragraph.strip()
    if current:
        parts.append(current)
    return parts


async def reindex(*, documents: Sequence[OKFDocument] = ()) -> dict:
    """Embed the OKF bundle into the vector store.

    Safe to run repeatedly: ids are stable, so this updates in place. Called
    from an admin endpoint or a deploy step, never during a farmer's request.
    """
    from AI_Backend.orchestration import llm
    from AI_Backend.agents.retrieval_agent import store

    if not llm.available():
        return {"status": "skipped", "reason": "No embedding key configured.",
                "chunks": 0}
    # The table is created by migration, never from here. If it is missing,
    # the deployment has not run `alembic upgrade head`; say so plainly.
    if not await store.available():
        return {"status": "skipped",
                "reason": "Vector store unavailable - run the database migration first.",
                "chunks": 0}

    docs = list(documents) or list(get_bundle().documents())
    chunks: List[Chunk] = []
    for document in docs:
        chunks.extend(chunk_document(document))

    if not chunks:
        return {"status": "empty", "reason": "No knowledge documents found.", "chunks": 0}

    written = 0
    for batch in _batched(chunks, EMBED_BATCH):
        try:
            vectors = await llm.embed([c.text for c in batch], model=EMBED_MODEL,
                                      input_type="passage")
        except llm.LLMUnavailable as exc:
            logger.error("Indexing stopped: %s", exc)
            return {"status": "partial", "reason": str(exc), "chunks": written}
        written += await store.upsert(batch, vectors)

    # Remove passages that were deleted from the handbook. Without this, text
    # withdrawn from the bundle keeps being retrieved and quoted to farmers.
    removed = await store.prune([c.chunk_id for c in chunks])

    logger.info("Knowledge reindexed | documents=%d chunks=%d removed=%d",
                len(docs), written, removed)
    return {"status": "ok", "documents": len(docs), "chunks": written,
            "removed": removed}


def _batched(items: Sequence, size: int) -> Iterable[Sequence]:
    for start in range(0, len(items), size):
        yield items[start:start + size]
