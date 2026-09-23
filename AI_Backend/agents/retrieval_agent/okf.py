"""
OKF — Open Knowledge Format bundles
====================================
The curated layer of the knowledge stack.

An OKF bundle is a folder of clean Markdown files plus a machine-readable
index (the "map"). An agent reads the map first - a few hundred tokens - and
learns what knowledge exists and where, instead of embedding the whole corpus
and hoping the right chunk comes back.

Why both OKF and RAG:

  OKF   curated, authoritative, stable: schemas, definitions, handbooks, the
        things that must be exactly right. Addressed by id, so retrieval is
        deterministic and costs no similarity search.
  RAG   discovery over a large, messy corpus: case studies, advisories, long
        logs. Fuzzy by nature, and used only when the curated layer does not
        already hold the answer.

The same Markdown feeds both: OKF files are clean, well-headed and small,
which makes them the best possible input to the chunker (see indexer.py).

Layout:

    knowledge/okf/
        okf.index.json          the map: id, title, summary, tags, path
        crops/groundnut.md          one document per crop
        practices/irrigation-scheduling.md
"""

from __future__ import annotations

import json
import logging
import pathlib
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Iterable, List, Optional, Sequence

logger = logging.getLogger("farmxpert.retrieval.okf")

from AI_Backend.agents.retrieval_agent.config import OKF_DIR as BUNDLE_DIR
from AI_Backend.agents.retrieval_agent.config import OKF_INDEX_NAME as INDEX_NAME


@dataclass(frozen=True)
class OKFEntry:
    """One curated document, as the map describes it."""
    id: str
    title: str
    summary: str
    path: str
    tags: tuple = ()
    crops: tuple = ()
    updated: Optional[str] = None
    authority: str = "farmxpert"      # who stands behind this text
    headings: tuple = ()              # section titles, the highest-signal metadata

    def score(self, terms: Sequence[str], crop: Optional[str] = None,
              body_stems: Optional[set] = None) -> float:
        """How well this entry's metadata answers the question.

        Weighted rather than counted: a term in the title or in a section
        heading says far more about what a document is for than the same term
        buried in a summary sentence. Headings matter most in practice - a
        question about "how long before harvest can I spray" should find the
        handbook whose section is called "Pre-harvest interval", not a crop
        page that happens to mention both words.

        The map is scored first and carries most of the weight; the body is
        consulted at low weight only to catch symptom wording. Reading it
        costs one cached pass over a small bundle, not a vector search.
        """
        fields = [(_stems(self.title), 3.0),
                  (_stems(" ".join(self.tags)), 3.0),
                  (_stems(" ".join(self.headings)), 2.5),
                  (_stems(self.summary), 1.0)]
        # The body counts too, at low weight. Farmers describe symptoms -
        # "my wheat is turning yellow" - and the word that matters is in the
        # prose, not in a heading. Weighted low so a passing mention never
        # outranks a document that is actually about the subject.
        if body_stems:
            fields.append((body_stems, 0.5))
        total = 0.0
        matched = set()
        for stems, weight in fields:
            for term in terms:
                if term in stems:
                    total += weight
                    matched.add(term)

        if crop and self.crops:
            wanted = crop.strip().lower()
            if wanted in {c.lower() for c in self.crops}:
                total += 3.0
                # Naming the crop IS a match, and a strong one. Counting it
                # toward breadth matters: "my wheat is turning yellow" overlaps
                # the wheat page on one word only, and without this the page
                # about the farmer's own crop scored too low to be returned.
                matched.add(wanted)
            else:
                total -= 2.0        # another crop's page is rarely what they want

        # A single weak overlap on a common word is not a match. Requiring
        # breadth keeps "soil" alone from pulling in every document.
        if len(matched) < min(2, len(terms)):
            total *= 0.4
        return total


@dataclass
class OKFDocument:
    id: str
    title: str
    text: str
    entry: OKFEntry
    sections: List[str] = field(default_factory=list)


class OKFBundle:
    """A loaded bundle. The map is held in memory; bodies are read on demand.

    Bodies are cached after first read: a bundle is small and changes only on
    deploy, so re-reading it per request would be waste.
    """

    def __init__(self, directory: pathlib.Path = BUNDLE_DIR) -> None:
        self.directory = directory
        self._entries: Dict[str, OKFEntry] = {}
        self._bodies: Dict[str, str] = {}
        self._body_stem_cache: Dict[str, set] = {}
        self._loaded_at: Optional[datetime] = None
        self.load()

    # ── loading ─────────────────────────────────────────────────────────

    def load(self) -> int:
        """Read the map. A missing or broken bundle is not fatal.

        The knowledge layer is an enhancement: without it the field agents
        still work, so a bad bundle degrades the answer instead of taking the
        farm's whole backend down.
        """
        self._entries.clear()
        self._bodies.clear()
        self._body_stem_cache.clear()
        index_path = self.directory / INDEX_NAME
        if not index_path.is_file():
            logger.warning("No OKF bundle at %s - curated knowledge is unavailable.",
                           self.directory)
            return 0
        try:
            raw = json.loads(index_path.read_text(encoding="utf-8"))
            for item in raw.get("documents", []):
                entry = OKFEntry(
                    id=str(item["id"]),
                    title=str(item.get("title", item["id"])),
                    summary=str(item.get("summary", "")),
                    path=str(item["path"]),
                    tags=tuple(item.get("tags", [])),
                    crops=tuple(item.get("crops", [])),
                    updated=item.get("updated"),
                    authority=str(item.get("authority", "farmxpert")),
                    headings=tuple(item.get("headings", [])))
                self._entries[entry.id] = entry
        except (OSError, ValueError, KeyError) as exc:
            logger.error("OKF index at %s is unusable: %s", index_path, exc)
            return 0

        self._loaded_at = datetime.now(timezone.utc)
        logger.info("OKF bundle loaded | documents=%d dir=%s",
                    len(self._entries), self.directory)
        return len(self._entries)

    # ── the map ─────────────────────────────────────────────────────────

    def map(self, *, crop: Optional[str] = None) -> List[dict]:
        """The cheap overview an agent reads before deciding anything."""
        entries = self._entries.values()
        if crop:
            wanted = crop.strip().lower()
            entries = [e for e in entries if not e.crops or wanted in
                       {c.lower() for c in e.crops}]
        return [{"id": e.id, "title": e.title, "summary": e.summary,
                 "tags": list(e.tags), "crops": list(e.crops)}
                for e in sorted(entries, key=lambda e: e.id)]

    def entries(self) -> List[OKFEntry]:
        return list(self._entries.values())

    def __len__(self) -> int:
        return len(self._entries)

    # ── addressing ──────────────────────────────────────────────────────

    def get(self, doc_id: str) -> Optional[OKFDocument]:
        """One document by id. Deterministic: no similarity, no ranking."""
        entry = self._entries.get(doc_id)
        if entry is None:
            return None
        body = self._body(entry)
        if body is None:
            return None
        return OKFDocument(id=entry.id, title=entry.title, text=body,
                           entry=entry, sections=_headings(body))

    def select(self, query: str, *, crop: Optional[str] = None,
               limit: int = 3) -> List[OKFDocument]:
        """The curated documents whose metadata best covers the question.

        Term overlap on the map, not semantic search: the curated layer is
        meant to be predictable, and anything needing fuzzy matching belongs
        in the RAG layer instead.
        """
        terms = _stem_list(_terms(query))
        if not terms:
            return []
        wanted = crop.strip().lower() if crop else None
        scored = []
        for entry in self._entries.values():
            # When the farmer names their crop, never hand back another
            # crop's page. Chickpea advice shown for a mustard question is
            # worse than one fewer passage: the answer step is told to use
            # the facts it is given, so an off-crop page invites a wrong dose
            # or a wrong stage. Practice handbooks carry no crop and always
            # stay eligible.
            if wanted and entry.crops and wanted not in {c.lower() for c in entry.crops}:
                continue
            score = entry.score(terms, crop=crop,
                                body_stems=self._body_stems(entry))
            if score >= MIN_SCORE:
                scored.append((score, entry))
        scored.sort(key=lambda pair: (-pair[0], pair[1].id))

        out: List[OKFDocument] = []
        for _score, entry in scored[:limit]:
            document = self.get(entry.id)
            if document:
                out.append(document)
        return out

    def documents(self) -> Iterable[OKFDocument]:
        """Every document, for the RAG indexer to chunk."""
        for entry in self._entries.values():
            document = self.get(entry.id)
            if document:
                yield document

    def _body_stems(self, entry: OKFEntry) -> set:
        """Stemmed body words, computed once per document and cached.

        The bundle is small and read from disk once, so this costs
        microseconds after the first question and saves a vector search.
        """
        cached = self._body_stem_cache.get(entry.id)
        if cached is None:
            cached = _stems(self._body(entry) or "")
            self._body_stem_cache[entry.id] = cached
        return cached

    def _body(self, entry: OKFEntry) -> Optional[str]:
        cached = self._bodies.get(entry.id)
        if cached is not None:
            return cached
        path = self.directory / entry.path
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            logger.warning("OKF document %s unreadable (%s): %s", entry.id, path, exc)
            return None
        self._bodies[entry.id] = text
        return text


# Below this a match is coincidence rather than relevance.
MIN_SCORE = 3.0

# A farmer says "salty", the handbook says "salinity"; a farmer says "spray",
# the handbook says "pesticide". Mapping the few dozen pairs that matter is
# cheaper, faster and far more predictable than embedding the curated layer.
SYNONYMS = {
    "salt": "salin", "salty": "salin", "saline": "salin", "salinity": "salin",
    "sodic": "salin", "ec": "salin", "alkali": "salin",
    "spray": "pesticid", "spraying": "pesticid", "pesticide": "pesticid",
    "insecticide": "pesticid", "fungicide": "pesticid", "chemical": "pesticid",
    "residue": "pesticid", "phi": "pesticid", "interval": "pesticid",
    "water": "irrig", "watering": "irrig", "irrigate": "irrig",
    "irrigation": "irrig", "moisture": "irrig", "drip": "irrig",
    "fertiliser": "fertil", "fertilizer": "fertil", "urea": "fertil",
    "npk": "fertil", "nitrogen": "fertil", "manure": "fertil", "dose": "fertil",
    "sow": "sow", "sowing": "sow", "seed": "sow", "planting": "sow",
    "plant": "sow", "seedbed": "sow", "germination": "sow",
    "harvest": "harvest", "harvesting": "harvest", "storage": "harvest",
    "store": "harvest", "drying": "harvest", "aflatoxin": "harvest",
    "frost": "weather", "heat": "weather", "storm": "weather",
    "hail": "weather", "wind": "weather", "rain": "weather",
    "pest": "pest", "disease": "pest", "blight": "pest", "borer": "pest",
    "aphid": "pest", "rust": "pest", "wilt": "pest", "rot": "pest",
}


def _stem(word: str) -> str:
    """Crude suffix stripping, then the synonym map. Good enough for a map."""
    if word in SYNONYMS:
        return SYNONYMS[word]
    for suffix in ("ation", "ing", "ers", "er", "ed", "es", "s"):
        if len(word) > 4 and word.endswith(suffix):
            word = word[: -len(suffix)]
            break
    return SYNONYMS.get(word, word)


def _stem_list(words: List[str]) -> List[str]:
    return list(dict.fromkeys(_stem(w) for w in words))


def _stems(text: str) -> set:
    return set(_stem_list(_terms(text)))


def _terms(query: str) -> List[str]:
    words = re.findall(r"[a-z]{3,}", (query or "").lower())
    return [w for w in words if w not in _STOPWORDS]


_STOPWORDS = {
    "the", "and", "for", "what", "how", "why", "when", "should", "can", "does",
    "are", "was", "will", "with", "from", "this", "that", "have", "has", "not",
    "you", "your", "our", "its", "about", "into", "than", "then", "there",
    "please", "tell", "give", "need", "want", "know", "farm", "crop",
}


def _headings(markdown: str) -> List[str]:
    return [line.lstrip("# ").strip()
            for line in markdown.splitlines() if line.startswith("#")]


_BUNDLE: Optional[OKFBundle] = None


def get_bundle() -> OKFBundle:
    """The process-wide bundle, loaded once."""
    global _BUNDLE
    if _BUNDLE is None:
        _BUNDLE = OKFBundle()
    return _BUNDLE


def reload_bundle() -> int:
    return get_bundle().load()
