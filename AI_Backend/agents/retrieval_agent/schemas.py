"""
Retrieval Agent — Schemas
==========================
Input: a question, and optionally the crop it is about.
Output: passages with their sources, and a record of how they were found.

The agent returns evidence, never prose. Writing the farmer's answer is the
orchestrator's job, and keeping the two apart is what stops a retrieval bug
from becoming a confident wrong answer.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class Source(str, Enum):
    """Which layer a passage came from.

    Worth distinguishing: curated text is authored and reviewed, indexed text
    is whatever was ingested. A reader deserves to know which they are reading.
    """
    OKF = "okf"           # curated handbook, addressed by id
    INDEX = "index"       # discovered by vector similarity


class RetrievalRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    question: str = Field(..., min_length=3, max_length=2000)
    question_en: Optional[str] = Field(
        None, max_length=2000,
        description="The question in English, from the understanding step. Lets the "
                    "English-indexed knowledge match a question asked in any language.")
    crop: Optional[str] = Field(
        None, description="Narrows curated documents and filters the index.")
    max_passages: int = Field(5, ge=1, le=20)
    allow_discovery: bool = Field(
        True, description="Permit the vector search. False keeps it to curated knowledge only.")


class Passage(BaseModel):
    title: str
    text: str
    source: Source
    doc_id: str
    similarity: Optional[float] = Field(
        None, ge=0.0, le=1.0,
        description="Cosine similarity. Absent for curated documents, which are addressed, not matched.")
    authority: Optional[str] = Field(
        None, description="Who stands behind this text.")


class RetrievalResult(BaseModel):
    question: str
    passages: List[Passage] = Field(default_factory=list)
    passage_count: int = 0
    sources: List[str] = Field(default_factory=list)

    retrieval_steps: List[str] = Field(
        default_factory=list,
        description="What the agent did and why - readable by a person debugging a bad answer.")
    searched_index: bool = False
    rewritten_query: Optional[str] = None

    curated_hits: int = 0
    indexed_hits: int = 0
    best_similarity: Optional[float] = None

    warnings: List[str] = Field(default_factory=list)
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def found_anything(self) -> bool:
        return bool(self.passages)
