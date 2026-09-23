"""
Retrieval Agent — test suite
=============================
Plain runner, no pytest:   python -m AI_Backend.tests.test_retrieval_agent

No network, no database, no embedding key. What is tested is the behaviour a
farmer depends on: the right handbook is found, an off-topic question returns
nothing rather than the least-bad page, the curated layer is preferred, the
agentic loop is bounded, and the published facts match what the agents
actually compute with.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
import traceback
from typing import Any, List

from AI_Backend.agents.retrieval_agent import tools
from AI_Backend.agents.retrieval_agent.agent import RetrievalAgent
from AI_Backend.agents.retrieval_agent.config import (
    GOOD_ENOUGH_SIMILARITY,
    MAX_REWRITES,
    OKF_DIR,
    OKF_EXCERPT_CHARS,
)
from AI_Backend.agents.retrieval_agent.okf import get_bundle
from AI_Backend.agents.retrieval_agent.schemas import (
    Passage,
    RetrievalRequest,
    RetrievalResult,
    Source,
)
from AI_Backend.agents.retrieval_agent.service import RetrievalService

logging.disable(logging.CRITICAL)

PASSED: List[str] = []
FAILED: List[str] = []
AGENT = RetrievalAgent()


def check(name: str, condition: Any, detail: Any = "") -> None:
    if condition:
        PASSED.append(name)
    else:
        FAILED.append(f"{name}: {detail}" if detail else name)


def case(fn):
    try:
        fn()
    except Exception:  # noqa: BLE001
        FAILED.append(f"{fn.__name__} raised:\n{traceback.format_exc()}")
    return fn


def ask(question: str, crop: str | None = None, **kw) -> RetrievalResult:
    payload = {"question": question, "crop": crop, **kw}
    return asyncio.run(AGENT.retrieve({k: v for k, v in payload.items() if v is not None}))


def ids(result: RetrievalResult) -> List[str]:
    return [p.doc_id for p in result.passages]


# ── 1. The bundle itself ────────────────────────────────────────────────────

@case
def test_bundle_covers_every_crop_the_agents_know():
    """Every crop any agent can name must have a handbook page.

    The crop predictor can recommend guar; if the knowledge base has no guar
    page, a farmer asking about the crop it just recommended gets nothing.
    """
    from AI_Backend.agents.crop_planning_growth.irrigation_planner.config import (
        CROP_CONFIG as IRRIGATION,
    )
    from AI_Backend.agents.crop_planning_growth.soil_health.config import CROP_CONFIG as SOIL
    from AI_Backend.agents.farm_operations_automation.task_scheduler.playbook import (
        CROP_PLAYBOOK,
    )

    known = set(SOIL) | set(IRRIGATION) | set(CROP_PLAYBOOK)
    documented = {c for entry in get_bundle().entries() for c in entry.crops}
    missing = sorted(known - documented)
    check(f"all {len(known)} agent crops have a document", not missing, missing)


@case
def test_every_indexed_document_exists_on_disk():
    bundle = get_bundle()
    missing = [e.id for e in bundle.entries() if bundle.get(e.id) is None]
    check("no index entry points at a missing file", not missing, missing)
    check("the bundle is not empty", len(bundle) >= 20, len(bundle))


@case
def test_every_document_has_headings_and_a_summary():
    thin = [e.id for e in get_bundle().entries()
            if not e.headings or len(e.summary) < 20]
    check("every document is described and sectioned", not thin, thin)


@case
def test_published_facts_match_the_agent_configuration():
    """The handbook must not drift from what the agents compute.

    Generated from the configs for exactly this reason; this test is what
    keeps a stale bundle from shipping after a config change.
    """
    from AI_Backend.agents.crop_planning_growth.irrigation_planner.config import (
        CROP_CONFIG as IRRIGATION,
    )

    bundle = get_bundle()
    drifted: List[str] = []
    for crop in ("groundnut", "rice", "cotton", "guar", "wheat"):
        document = bundle.get(f"crop.{crop}")
        if document is None:
            drifted.append(f"{crop}: no document")
            continue
        config = IRRIGATION.get(crop) or {}
        depth = config.get("root_depth_m")
        if depth is not None and f"| Root depth (m) | {depth} |" not in document.text:
            drifted.append(f"{crop}: root depth {depth} not published")
        season = config.get("season_days")
        if season is not None and f"| Season length (days) | {season} |" not in document.text:
            drifted.append(f"{crop}: season {season} not published")
    check("published facts match the live config", not drifted, drifted)


@case
def test_bundle_survives_a_missing_directory():
    """A broken bundle degrades the answer; it never takes the backend down."""
    import pathlib

    from AI_Backend.agents.retrieval_agent.okf import OKFBundle

    empty = OKFBundle(pathlib.Path(__file__).parent / "does-not-exist")
    check("a missing bundle loads as empty", len(empty) == 0)
    check("selecting from it returns nothing", empty.select("irrigation") == [])
    check("the real bundle is untouched", len(get_bundle()) >= 20)


# ── 2. Finding the right thing ──────────────────────────────────────────────

@case
def test_questions_find_the_right_handbook():
    expected = [
        ("when should I irrigate guar", "guar", "crop.guar"),
        ("how long before harvest can I spray", None, "practice.pesticide-safety"),
        ("what causes blossom end rot in tomato", "tomato", "crop.tomato"),
        ("how do I fix salty soil", None, "practice.soil-salinity"),
        ("how much urea should I apply", None, "practice.fertilizer-use"),
        ("will frost damage my crop", None, "practice.weather-risk"),
        ("how do I store groundnut safely", "groundnut", "practice.harvest-and-storage"),
        ("why are my cabbage heads splitting", "cabbage", "crop.cabbage"),
        ("aphids on my mustard pods", "mustard", "crop.mustard"),
        ("when should I sow", None, "practice.sowing-and-seedbed"),
    ]
    for question, crop, wanted in expected:
        found = ids(ask(question, crop))
        check(f"'{question[:34]}' finds {wanted}", wanted in found, found)


@case
def test_a_symptom_finds_the_crop_page():
    """Farmers describe symptoms, not chapter titles."""
    check("a symptom in the body is findable",
          "crop.wheat" in ids(ask("my wheat is turning yellow", "wheat")),
          ids(ask("my wheat is turning yellow", "wheat")))


@case
def test_naming_a_crop_prefers_that_crop():
    found = ids(ask("when should I irrigate", "rice"))
    others = [i for i in found if i.startswith("crop.") and i != "crop.rice"]
    check("another crop's page is not returned", not others, found)


@case
def test_an_off_topic_question_returns_nothing():
    """The classic RAG failure is answering confidently from the least-bad
    page. Nothing is the correct answer here."""
    for question in ("what is the price of gold", "who won the cricket match",
                     "how do I reset my phone"):
        result = ask(question)
        check(f"'{question[:28]}' returns nothing", result.passage_count == 0, ids(result))
        check(f"'{question[:28]}' says so", any("No knowledge" in w for w in result.warnings),
              result.warnings)


@case
def test_nothing_is_fabricated_when_empty():
    result = ask("who won the cricket match")
    check("no passages", result.passages == [])
    check("no sources", result.sources == [])
    check("the steps still explain what was tried", len(result.retrieval_steps) >= 1,
          result.retrieval_steps)


# ── 3. The bounded agentic loop ─────────────────────────────────────────────

@case
def test_curated_knowledge_stops_the_search_early():
    """The point of a curated layer: when it answers, spend nothing more."""
    result = ask("when should I irrigate guar", "guar")
    check("two curated documents were enough", result.curated_hits >= 2, result.curated_hits)
    check("the index was not searched", result.searched_index is False)
    check("the decision is recorded",
          any("no index search" in s.lower() for s in result.retrieval_steps),
          result.retrieval_steps)


@case
def test_discovery_is_attempted_when_curated_is_thin(monkey=None):
    """With one curated hit, the agent should try the index."""
    calls = {"available": 0}
    original = tools.index_available

    async def fake_available():
        calls["available"] += 1
        return False

    tools.index_available = fake_available
    try:
        result = ask("what causes blossom end rot in tomato", "tomato")
        check("the index was consulted when curated was thin",
              calls["available"] >= 1 or result.curated_hits >= 2,
              (calls, result.curated_hits))
    finally:
        tools.index_available = original


@case
def test_index_failure_does_not_lose_curated_results():
    original_available, original_search = tools.index_available, tools.vector_search

    async def available():
        return True

    async def exploding(*_args, **_kwargs):
        raise RuntimeError("pgvector is down")

    tools.index_available, tools.vector_search = available, exploding
    try:
        result = ask("what causes blossom end rot in tomato", "tomato")
        check("curated passages survive an index failure", result.passage_count >= 1,
              ids(result))
        check("the failure is reported, not hidden",
              any("failed" in w.lower() for w in result.warnings), result.warnings)
    finally:
        tools.index_available, tools.vector_search = original_available, original_search


@case
def test_the_rewrite_happens_at_most_once():
    """A retrieval agent that keeps rewriting is an unbounded bill."""
    searches: List[str] = []
    original_available = tools.index_available
    original_search = tools.vector_search
    original_rewrite = tools.rewrite_query

    async def available():
        return True

    async def weak_search(question, crop=None, limit=5):
        searches.append(question)
        return [Passage(title="Something", text="barely related text",
                        source=Source.INDEX, doc_id="index.weak", similarity=0.1)]

    async def rewrite(question, crop=None):
        return f"rewritten {question}"

    tools.index_available, tools.vector_search = available, weak_search
    tools.rewrite_query = rewrite
    try:
        result = ask("what causes blossom end rot in tomato", "tomato")
        check("the index was searched at most twice", len(searches) <= 1 + MAX_REWRITES,
              searches)
        check("the rewrite is recorded", result.rewritten_query is not None
              or len(searches) == 1, result.rewritten_query)
    finally:
        tools.index_available = original_available
        tools.vector_search = original_search
        tools.rewrite_query = original_rewrite


@case
def test_a_better_rewrite_wins_and_a_worse_one_does_not():
    original_available = tools.index_available
    original_search = tools.vector_search
    original_rewrite = tools.rewrite_query

    async def available():
        return True

    async def rewrite(question, crop=None):
        return "technical phrasing"

    def searcher(second_score: float):
        async def search(question, crop=None, limit=5):
            score = second_score if question == "technical phrasing" else 0.1
            return [Passage(title="P", text="text", source=Source.INDEX,
                            doc_id=f"index.{question[:6]}", similarity=score)]
        return search

    tools.index_available, tools.rewrite_query = available, rewrite
    try:
        tools.vector_search = searcher(0.9)
        better = ask("blossom end rot tomato", "tomato")
        check("a better rewrite is used",
              any(p.doc_id.startswith("index.techni") for p in better.passages),
              ids(better))

        tools.vector_search = searcher(0.05)
        worse = ask("blossom end rot tomato", "tomato")
        check("a worse rewrite is discarded",
              not any(p.doc_id.startswith("index.techni") for p in worse.passages),
              ids(worse))
    finally:
        tools.index_available = original_available
        tools.vector_search = original_search
        tools.rewrite_query = original_rewrite


@case
def test_discovery_can_be_switched_off():
    called = {"n": 0}
    original = tools.index_available

    async def available():
        called["n"] += 1
        return True

    tools.index_available = available
    try:
        result = ask("what causes blossom end rot in tomato", "tomato",
                     allow_discovery=False)
        check("the index is never touched", called["n"] == 0, called)
        check("the reason is recorded",
              any("not permitted" in s for s in result.retrieval_steps),
              result.retrieval_steps)
    finally:
        tools.index_available = original


# ── 4. Contract and robustness ──────────────────────────────────────────────

@case
def test_passages_are_capped_and_excerpted():
    result = ask("irrigation water salinity harvest spray fertilizer sowing", max_passages=3)
    check("the cap is respected", result.passage_count <= 3, result.passage_count)
    check("long documents are excerpted",
          all(len(p.text) <= OKF_EXCERPT_CHARS for p in result.passages),
          [len(p.text) for p in result.passages])
    check("the count matches the list", result.passage_count == len(result.passages))


@case
def test_curated_passages_carry_their_authority():
    result = ask("how long before harvest can I spray")
    curated = [p for p in result.passages if p.source == Source.OKF]
    check("curated passages are marked as curated", curated, ids(result))
    check("they name who stands behind them",
          all(p.authority for p in curated), [p.authority for p in curated])
    check("they carry no similarity score",
          all(p.similarity is None for p in curated))


@case
def test_input_shapes_are_accepted():
    plain = asyncio.run(AGENT.retrieve("how do I fix salty soil"))
    check("a bare question string works", plain.passage_count >= 1, ids(plain))

    state = asyncio.run(AGENT.retrieve(
        {"farmer_query": "how do I fix salty soil", "crop": {"name": "cotton"}}))
    check("orchestrator state works", state.passage_count >= 1, ids(state))

    typed = asyncio.run(AGENT.retrieve(
        RetrievalRequest(question="how do I fix salty soil")))
    check("a typed request works", typed.passage_count >= 1)


@case
def test_bad_input_is_rejected_cleanly():
    for bad in ({}, {"question": ""}, {"question": "hi"}, 42):
        try:
            asyncio.run(AGENT.retrieve(bad))
            check(f"{str(bad)[:18]} is rejected", False, "accepted")
        except Exception as exc:  # noqa: BLE001
            check(f"{str(bad)[:18]} is rejected", True)
            check("the error is not an internal crash",
                  type(exc).__name__ in ("ValidationError", "TypeError", "ValueError"),
                  type(exc).__name__)


@case
def test_langgraph_node_never_raises():
    check("junk state returns no update", asyncio.run(AGENT({"nothing": True})) == {})
    good = asyncio.run(AGENT({"farmer_query": "how do I fix salty soil"}))
    check("a real question returns knowledge", "knowledge" in good)
    check("the payload is JSON-safe", json.dumps(good["knowledge"]))


@case
def test_result_is_json_safe_and_complete():
    result = asyncio.run(AGENT.run({"question": "when should I irrigate guar",
                                    "crop": "guar"}))
    text = json.dumps(result)
    check("the whole result serialises", len(text) > 200)
    for field in ("question", "passages", "passage_count", "sources",
                  "retrieval_steps", "searched_index", "retrieved_at"):
        check(f"{field} is present", field in result, sorted(result))


@case
def test_health_reports_what_is_reachable():
    health = AGENT.health()
    check("it names the agent", health["agent"] == "retrieval_agent")
    check("it counts curated documents", health["curated_documents"] >= 20, health)
    check("it states the embedding status",
          health["embeddings"] in ("configured", "not configured"), health)


# ── 5. Orchestration adapter ────────────────────────────────────────────────

@case
def test_the_orchestration_adapter_wraps_this_agent():
    from AI_Backend.orchestration.agents.retrieval_agent import build_retrieval
    from AI_Backend.orchestration.contracts import Capability, ExecutionContext

    spec = build_retrieval()
    check("it declares the knowledge capability",
          Capability.KNOWLEDGE_ANSWER in spec.capabilities)
    check("it requires a question", "farmer_query" in spec.requires_context)
    check("it is best effort", spec.criticality.value == "best_effort")

    context = ExecutionContext(request_id="t", farmer_query="how do I fix salty soil",
                               crop={"name": "cotton"})
    raw = asyncio.run(spec.execute(context))
    output = spec.validate_output(raw)
    check("the adapter returns validated output", output.data["passage_count"] >= 1)
    check("curated results carry confidence", output.confidence is not None)
    check("sources are surfaced", output.sources, output.sources)


@case
def test_the_adapter_rejects_a_malformed_result():
    from AI_Backend.orchestration.agents.retrieval_agent import build_retrieval
    from AI_Backend.orchestration.engine import AgentOutputError

    spec = build_retrieval()
    for bad in ({"passages": "not a list", "passage_count": 0},
                {"passage_count": 3, "passages": []},
                {"no_passages_key": True}):
        try:
            spec.validate_output(bad)
            check(f"{str(bad)[:26]} is rejected", False, "accepted")
        except AgentOutputError:
            check(f"{str(bad)[:26]} is rejected", True)


# ── 6. The bundle builder (regression guards from the agronomic review) ─────

@case
def test_no_tag_is_shared_by_every_crop():
    """Tags are weighted heavily in selection, so they must distinguish.

    The builder once added the section names (water, nutrition, problems,
    harvest) to every crop, giving all 19 pages four identical high-weight
    tags. An unrelated crop then outranked the right handbook.
    """
    from collections import Counter

    crop_entries = [e for e in get_bundle().entries() if e.crops]
    counts = Counter(tag for entry in crop_entries for tag in entry.tags)
    universal = [tag for tag, n in counts.items()
                 if n == len(crop_entries) and tag != "crop"]
    check("no tag is on every crop page", not universal, universal)
    check("each crop still carries distinguishing tags",
          all(len(e.tags) >= 4 for e in crop_entries),
          [(e.id, len(e.tags)) for e in crop_entries if len(e.tags) < 4])


@case
def test_every_crop_states_its_season():
    """A rabi and a kharif crop are managed differently; the page must say which."""
    from AI_Backend.knowledge.build_okf import CROP_NOTES

    bundle = get_bundle()
    silent = []
    for crop in CROP_NOTES:
        document = bundle.get(f"crop.{crop.replace(' ', '-')}")
        if document is None or "Season:" not in document.text:
            silent.append(crop)
    check("every crop page states its season", not silent, silent)


@case
def test_handbooks_do_not_contradict_each_other_on_spray_wind():
    """Two pages once gave different spray wind limits - 15 and 39 km/h.

    A farmer reading only the weather page would have sprayed at 30 km/h and
    drifted onto a neighbour's field. Cross-document consistency on a safety
    limit is worth a test.
    """
    bundle = get_bundle()
    pesticide = bundle.get("practice.pesticide-safety")
    weather = bundle.get("practice.weather-risk")
    check("both handbooks exist", pesticide and weather)
    if not (pesticide and weather):
        return

    # Only lines about the ACT of spraying. A line about sprayer booms being
    # unsafe at gale force is a different limit and legitimately differs: 15
    # km/h is where the spray drifts, 39 km/h is where the equipment and the
    # person are at risk.
    spraying = [line for line in weather.text.splitlines()
                if "spraying" in line.lower() and "km/h" in line]
    check("the weather page states the spray limit", spraying, weather.text[:300])
    for line in spraying:
        check("it quotes the same 15 km/h limit", "15 km/h" in line, line)
    check("the pesticide page states the limit", "15 km/h" in pesticide.text)
    check("the two pages agree on the number",
          "15 km/h" in weather.text and "15 km/h" in pesticide.text)


@case
def test_salt_tolerance_is_labelled_as_ece():
    """ECe from a laboratory paste extract and a field meter's 1:2 reading are
    different numbers. Publishing one as the other invites a real field error."""
    document = get_bundle().get("crop.guar")
    check("the guar page exists", document is not None)
    if document is None:
        return
    check("the threshold is marked ECe", "(ECe)" in document.text, document.text[:600])
    check("the difference is explained",
          "saturated paste" in document.text and "1:2" in document.text)


@case
def test_depletion_fraction_is_explained_not_just_printed():
    """`p = 0.55` means nothing to a farmer without the sentence beside it."""
    document = get_bundle().get("crop.guar")
    if document is None:
        return
    check("p is glossed in plain words",
          "available water" in document.text and "55 percent" in document.text,
          document.text[:900])


@case
def test_facts_table_never_prints_none():
    """A config missing a value must drop the row, not publish the word None."""
    from AI_Backend.knowledge.build_okf import _facts_section

    partial = _facts_section({"soil": {"salinity": {"threshold": 2.5}},   # no slope
                              "irrigation": {"root_depth_m": None}})
    text = "\n".join(partial)
    check("no None reaches the page", "None" not in text, text)
    check("the threshold is still published", "2.5" in text, text)
    check("the missing slope is simply absent", "% of yield" not in text, text)

    check("an empty config renders nothing", _facts_section({}) == [])


@case
def test_builder_reports_crops_it_has_no_prose_for():
    """A crop an agent can name but the handbook cannot describe is a silent
    gap; the build must say so rather than quietly omit it."""
    from AI_Backend.knowledge.build_okf import undocumented_agent_crops

    missing = undocumented_agent_crops()
    check("every agent crop has a handbook entry", not missing, missing)


@case
def test_rebuilding_is_deterministic():
    """Two builds of unchanged sources must produce identical documents.

    Otherwise every regeneration churns the bundle and re-embeds it for no
    reason.
    """
    import tempfile
    import pathlib as _pathlib

    from AI_Backend.knowledge.build_okf import build

    with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
        build(_pathlib.Path(first))
        build(_pathlib.Path(second))
        differing = []
        for path in sorted(_pathlib.Path(first).rglob("*.md")):
            other = _pathlib.Path(second) / path.relative_to(first)
            if not other.is_file() or other.read_text(encoding="utf-8") != \
                    path.read_text(encoding="utf-8"):
                differing.append(path.name)
        check("two builds agree", not differing, differing)


@case
def test_generated_pages_are_well_formed_markdown():
    bundle = get_bundle()
    problems = []
    for entry in bundle.entries():
        document = bundle.get(entry.id)
        if document is None:
            continue
        text = document.text
        if not text.startswith("# "):
            problems.append(f"{entry.id}: no title")
        if "\n\n\n" in text:
            problems.append(f"{entry.id}: blank-line run")
        # A half-rendered table row is the classic generator bug.
        for line in text.splitlines():
            if line.startswith("|") and line.count("|") != 3 and "---" not in line:
                problems.append(f"{entry.id}: malformed row {line[:40]}")
    check("every page is well formed", not problems, problems[:5])


@case
def test_no_page_says_the_same_thing_twice():
    """Near-identical passages get embedded twice, so a search returns the
    same sentence in two slots and crowds out everything else."""
    import re

    from AI_Backend.knowledge.build_okf import _key

    bundle = get_bundle()
    repeats = []
    for entry in bundle.entries():
        document = bundle.get(entry.id)
        if document is None:
            continue
        bullets = [re.sub(r"^[-\s]*(Do: |Do not: )?", "", line).strip()
                   for line in document.text.splitlines() if line.startswith("- ")]
        keys = [(b, _key(b)) for b in bullets]
        for i, (text_a, key_a) in enumerate(keys):
            for text_b, key_b in keys[i + 1:]:
                if not key_a or not key_b:
                    continue
                contained = len(key_a & key_b) / min(len(key_a), len(key_b))
                if contained > 0.6:
                    repeats.append((entry.id, text_a[:50], text_b[:50]))
    check("no sentence is repeated on a page", not repeats, repeats[:3])


@case
def test_every_agent_rule_appears_on_its_crop_page():
    """The scheduler's rules are the operational truth. If prose could
    suppress one, editing a rule would silently fail to reach the handbook."""
    from AI_Backend.agents.farm_operations_automation.task_scheduler.playbook import (
        CROP_PLAYBOOK,
    )

    bundle = get_bundle()
    missing = []
    for crop, categories in CROP_PLAYBOOK.items():
        document = bundle.get(f"crop.{crop.replace(' ', '-')}")
        if document is None:
            missing.append(f"{crop}: no page")
            continue
        for category, rules in categories.items():
            for rule in list(rules.get("do", [])) + list(rules.get("do_not", [])):
                if rule not in document.text:
                    missing.append(f"{crop}/{category}: {rule[:40]}")
    check("every scheduler rule reaches the handbook", not missing, missing[:3])


@case
def test_deduplication_prefers_the_rule_over_the_prose():
    """Direction matters: a stale sentence must never hide a changed rule."""
    from AI_Backend.knowledge.build_okf import _already_covered, _key

    # Lexical containment, so it catches a reworded duplicate - not a full
    # paraphrase. Where prose says the same thing in entirely different words
    # ("waterlogging" against "water stand"), the source text is fixed
    # instead; no test pretends the matcher is smarter than it is.
    rule = "Do not swing between dry and heavy watering during head formation - the heads split."
    prose = ("Do not swing between dry and heavy watering during head formation - "
             "the heads split and lose all market value.")
    check("prose duplicating a rule is dropped",
          _already_covered(prose, [_key(rule)]), (prose, rule))
    check("distinct advice is kept",
          not _already_covered("Inoculate the seed with rhizobium at sowing.",
                               [_key(rule)]))
    check("an empty sentence is never 'covered'", not _already_covered("", [_key(rule)]))
    check("no rules means nothing is covered", not _already_covered(prose, []))


@case
def test_no_crop_page_is_left_with_only_a_table():
    bundle = get_bundle()
    bare = []
    for entry in bundle.entries():
        if not entry.crops:
            continue
        document = bundle.get(entry.id)
        if document and "## " not in document.text.split("## Field facts")[-1]:
            bare.append(entry.id)
    check("every crop page carries guidance, not just numbers", not bare, bare)


# ── runner ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print(f"\n{len(PASSED) + len(FAILED)} checks\n")
    for failure in FAILED:
        print("  FAIL", failure)
    print(f"\n{len(PASSED)}/{len(PASSED) + len(FAILED)} checks passed\n")
    sys.exit(1 if FAILED else 0)
