"""
Retrieval Agent — Configuration
================================
Where the knowledge lives, how far the agent may go to find it, and when it
should stop looking.

The limits here exist to bound cost. An agent that keeps rewriting its query
and searching again will answer slightly better and cost without limit, so
every loop in this agent has a hard ceiling set below.
"""

from __future__ import annotations

import os
import pathlib
from typing import Final


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


# ── Agent identity ──────────────────────────────────────────────────────────

AGENT_ID:      Final[str] = "retrieval_agent"
AGENT_VERSION: Final[str] = "2.0.0"
AGENT_NAME:    Final[str] = "Knowledge Retrieval"


# ── Curated layer (OKF) ─────────────────────────────────────────────────────
# A bundle of clean Markdown plus an index that lists what exists. The agent
# reads the index first - a few hundred tokens - instead of searching a corpus
# it may not need.

OKF_DIR: Final[pathlib.Path] = pathlib.Path(os.getenv(
    "FARMXPERT_OKF_DIR",
    str(pathlib.Path(__file__).resolve().parents[2] / "knowledge" / "okf")))

OKF_INDEX_NAME: Final[str] = "okf.index.json"

# How many curated documents to return, and how many constitute "enough".
# Two well-matched handbook entries answer most farmer questions; going to the
# vector index after that spends an embedding call to add little.
OKF_MAX_DOCUMENTS: Final[int] = _env_int("FARMXPERT_OKF_MAX_DOCS", 2)
OKF_ENOUGH_DOCUMENTS: Final[int] = _env_int("FARMXPERT_OKF_ENOUGH", 2)

# A curated document is trimmed to this many characters when returned, so one
# long handbook page cannot dominate the prompt.
OKF_EXCERPT_CHARS: Final[int] = _env_int("FARMXPERT_OKF_EXCERPT", 2000)


# ── Discovery layer (pgvector) ──────────────────────────────────────────────

VECTOR_TABLE: Final[str] = os.getenv("FARMXPERT_RAG_TABLE", "knowledge_chunks")
# The index width. OpenAI text-embedding-3 is asked for this width; NVIDIA
# nv-embedqa-e5-v5 is natively 1024. Changing it means a new column and a reindex.
EMBED_DIM: Final[int] = _env_int("EMBED_DIM", _env_int("FARMXPERT_RAG_DIM", 1024))
EMBED_MODEL: Final[str] = (os.getenv("EMBED_MODEL") or os.getenv("NVIDIA_EMBED_MODEL")
                          or ("text-embedding-3-small" if "api.openai.com" in os.getenv("LLM_BASE_URL", "")
                              else "nvidia/nv-embedqa-e5-v5"))

MAX_PASSAGES: Final[int] = _env_int("FARMXPERT_RAG_PASSAGES", 5)

# Below this cosine similarity a passage is noise. Returning the least-bad
# match for a question the corpus does not cover is the classic RAG failure:
# it reads as confident and is wrong.
MIN_SIMILARITY: Final[float] = _env_float("FARMXPERT_RAG_MIN_SIMILARITY", 0.25)

# Below this, the results are weak enough to be worth one query rewrite.
GOOD_ENOUGH_SIMILARITY: Final[float] = _env_float("FARMXPERT_RAG_GOOD_ENOUGH", 0.45)

# The hard ceiling on the agentic loop. One rewrite, never more.
MAX_REWRITES: Final[int] = 1


# ── Indexing ────────────────────────────────────────────────────────────────

MAX_CHUNK_CHARS: Final[int] = 1200
MIN_CHUNK_CHARS: Final[int] = 120
EMBED_BATCH: Final[int] = 32
