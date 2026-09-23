"""Multilingual understanding, answering, retrieval and streaming.

    python -m AI_Backend.tests.test_multilingual
    FARMXPERT_LIVE_EVAL=1 python -m AI_Backend.tests.test_multilingual   # + real model

Offline everything runs against a fake provider. The live mode sends the
evaluation set through the configured model and reports accuracy per language.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from contextlib import contextmanager
from pathlib import Path

import httpx

from AI_Backend.orchestration import languages, llm

PASSED, FAILED = [], []
EVAL = json.loads((Path(__file__).parent / "data" / "multilingual_eval.json").read_text("utf-8"))


def check(name, ok, detail=""):
    (PASSED if ok else FAILED).append(name if ok else f"{name} -> {detail}")
    print(("  [PASS] " if ok else "  [FAIL] ") + name + ("" if ok else f"  ({detail})"))


@contextmanager
def env(**values):
    keys = ("LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL_ANSWER", "LLM_MODEL_UNDERSTAND",
            "LLM_MODEL_FALLBACK", "NVIDIA_API_KEY", "EMBED_DIM")
    saved = {k: os.environ.pop(k, None) for k in keys}
    os.environ.update(values)
    try:
        yield
    finally:
        for k in keys:
            os.environ.pop(k, None)
        os.environ.update({k: v for k, v in saved.items() if v is not None})


# ── deterministic detection, every evaluation row ───────────────────────────

wrong = []
for case in EVAL["cases"]:
    d = languages.detect(case["text"], case.get("hint"))
    if d.script != case["script"]:
        wrong.append((case["text"][:30], "script", d.script, case["script"]))
    # Without the model, shared scripts fall back to the hint or a default;
    # only pinned scripts, English and hinted rows must be exact here.
    must_match = d.pinned or case.get("hint") or case["language"] == "en"
    if must_match and d.language != case["language"]:
        wrong.append((case["text"][:30], "language", d.language, case["language"]))
check(f"script detected for all {len(EVAL['cases'])} evaluation questions", not wrong, wrong)

check("a stray unit does not make Hindi look Latin", languages.detect_script("मिट्टी का pH 8.2 है") == "deva")
check("romanized Hindi is not English", languages.detect("kheti mein khad kab dalu?").language == "hi")
check("plain English stays English even with a Hindi profile",
      languages.detect("How much fertilizer for wheat?", "hi").language == "en")
check("codes are normalised", [languages.normalise_code(x) for x in ("hi-IN", "Gujarati", "tam", "xx")]
      == ["hi", "gu", "ta", None])
check("a model's wrong language loses to a pinned script",
      languages.reconcile("hi", languages.detect("என் நெல் வயல்")) == "ta")
check("a model's language wins inside a shared script",
      languages.reconcile("mr", languages.detect("माझ्या सोयाबीनला खत")) == "mr")
check("a model's language that cannot be written in this script is refused",
      languages.reconcile("ta", languages.detect("आमार धान")) != "ta")
check("all 22 scheduled languages and English are registered", len(languages.LANGUAGES) == 23)

ins = languages.answer_instruction("hi", "latn")
check("romanized question -> romanized answer", "Latin" in ins and "romanized Hindi" in ins, ins)
check("native script question -> native script answer",
      "Gujarati script" in languages.answer_instruction("gu", "gujr"))


# ── prompts ─────────────────────────────────────────────────────────────────

with env(LLM_API_KEY="k"):
    system, user = llm.answer_prompt("pani kab du?", {"irrigation_planner": {"depth_mm": 25}},
                                     language="hi", script="latn", mode="voice")
check("answer prompt carries the script instruction", "romanized Hindi" in user)
check("voice mode adds speakable-answer rules", "SPOKEN" in system and "millimetre" in system)
check("text mode does not", "SPOKEN" not in llm.answer_prompt(
    "q", {"a": {"x": 1}}, language="en", script="latn")[0])
check("voice answers get a smaller budget", llm.answer_budget("voice") < llm.answer_budget("text"))


# ── understanding with a fake model ─────────────────────────────────────────

def model_reply(content):
    def provider(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"model": "gpt-5-nano",
                                         "choices": [{"message": {"content": content}}],
                                         "usage": {"prompt_tokens": 90, "completion_tokens": 30}})
    return provider


def run_with(provider, factory):
    async def go():
        loop = asyncio.get_running_loop()
        llm._CLIENTS[loop] = httpx.AsyncClient(transport=httpx.MockTransport(provider))
        try:
            return await factory()
        finally:
            await llm._CLIENTS.pop(loop).aclose()
    return asyncio.run(go())


with env(LLM_API_KEY="k", LLM_BASE_URL="https://api.openai.com/v1"):
    u = run_with(model_reply('{"intent":"irrigation","crop":"Rice","language":"hi",'
                             '"query_en":"When should I water my paddy field?","confidence":0.9}'),
                 lambda: llm.understand("என் நெல் வயலுக்கு எப்போது தண்ணீர்?"))
    check("understanding: Tamil script overrides the model's 'hi'", u["language"] == "ta", u)
    check("understanding: English rendering and crop kept",
          (u["query_en"], u["crop"], u["confidence"], u["script"])
          == ("When should I water my paddy field?", "rice", 0.9, "taml"), u)
    check("understanding: tier reported", u["tier"] == "strong")

    u = run_with(model_reply("not json at all"), lambda: llm.understand("मेरे गेहूं में पानी?"))
    check("unusable model reply -> safe default, still in the farmer's language",
          (u["intent"].value, u["language"], u["source"]) == ("ask", "hi", "detected"), u)

with env():
    u = asyncio.run(llm.understand("ਮੇਰੀ ਕਣਕ ਨੂੰ ਪਾਣੀ"))
    check("no model configured -> language still detected", (u["language"], u["script"]) == ("pa", "guru"), u)


# ── retrieval: English rendering reaches both layers ────────────────────────

from AI_Backend.agents.retrieval_agent import tools  # noqa: E402
from AI_Backend.agents.retrieval_agent.schemas import Passage, RetrievalRequest, Source  # noqa: E402
from AI_Backend.agents.retrieval_agent.service import RetrievalService  # noqa: E402


def passage(doc, sim):
    return Passage(title=doc, text=f"text of {doc}", source=Source.INDEX, doc_id=doc, similarity=sim)


merged = tools.rrf_merge([[passage("a", 0.5), passage("b", 0.4)], [passage("b", 0.8), passage("c", 0.7)]])
check("rank fusion: found by both lists ranks first, keeps its best similarity",
      [p.doc_id for p in merged] == ["b", "a", "c"] and merged[0].similarity == 0.8,
      [(p.doc_id, p.similarity) for p in merged])

calls = {"okf": [], "multi": [], "single": 0, "rewrite": 0}
saved = (tools.okf_select, tools.vector_search_multi, tools.vector_search, tools.rewrite_query,
         tools.index_available)


async def fake_available():
    return True


async def fake_multi(questions, crop=None, limit=5):
    calls["multi"].append(list(questions))
    return [passage("irrigation-wheat", 0.1)]   # weak: would normally trigger a rewrite


async def fake_single(*a, **k):
    calls["single"] += 1
    return []


async def fake_rewrite(*a, **k):
    calls["rewrite"] += 1
    return None

tools.okf_select = lambda q, crop=None, limit=3: calls["okf"].append(q) or []
tools.vector_search_multi, tools.vector_search = fake_multi, fake_single
tools.rewrite_query, tools.index_available = fake_rewrite, fake_available
try:
    asyncio.run(RetrievalService().retrieve(RetrievalRequest(
        question="मेरे गेहूं में पानी कब दूं?", question_en="When should I irrigate my wheat?")))
finally:
    (tools.okf_select, tools.vector_search_multi, tools.vector_search, tools.rewrite_query,
     tools.index_available) = saved
check("curated layer is matched with the English rendering too",
      calls["okf"] == ["मेरे गेहूं में पानी कब दूं?", "When should I irrigate my wheat?"], calls["okf"])
check("index is searched with both phrasings in one call",
      calls["multi"] == [["मेरे गेहूं में पानी कब दूं?", "When should I irrigate my wheat?"]]
      and calls["single"] == 0, calls)
check("no extra rewrite call when an English rendering exists", calls["rewrite"] == 0)


# ── streaming through the orchestrator ──────────────────────────────────────

def streaming_provider(request: httpx.Request) -> httpx.Response:
    body = json.loads(request.content)
    if not body.get("stream"):
        return httpx.Response(200, json={"choices": [{"message": {"content":
            '{"intent":"ask","crop":null,"language":"hi","query_en":"What is mulching?","confidence":0.8}'}}],
            "usage": {"prompt_tokens": 50, "completion_tokens": 20}})
    chunks = ["मल्चिंग ", "से नमी ", "बचती है।"]
    lines = [f'data: {json.dumps({"model": body["model"], "choices": [{"delta": {"content": c}}]})}'
             for c in chunks]
    lines.append('data: {"choices": [], "usage": {"prompt_tokens": 400, "completion_tokens": 12}}')
    lines.append("data: [DONE]")
    return httpx.Response(200, text="\n\n".join(lines) + "\n\n",
                          headers={"content-type": "text/event-stream"})


async def collect_stream():
    from AI_Backend.orchestration.agents import register_all
    from AI_Backend.orchestration.schemas import OrchestrationRequest
    from AI_Backend.orchestration.service import OrchestratorService
    register_all()
    events = []
    async for name, payload in OrchestratorService().stream(OrchestrationRequest(
            query="मल्चिंग क्या है?", explain=True)):
        events.append((name, payload))
    return events

with env(LLM_API_KEY="k", LLM_BASE_URL="https://api.openai.com/v1", LLM_MODEL_ANSWER="gpt-5",
         LLM_MODEL_UNDERSTAND="gpt-5-nano"):
    events = run_with(streaming_provider, collect_stream)
names = [n for n, _ in events]
check("stream ends with done, exactly once", names[-1] == "done" and names.count("done") == 1, names)
if "meta" in names:
    done = events[-1][1]
    deltas = "".join(p["text"] for n, p in events if n == "delta")
    check("meta comes before any delta", names.index("meta") < (names.index("delta") if "delta" in names else 99))
    check("done carries the whole streamed answer", done["answer"] == deltas.strip() and deltas, (done["answer"], deltas))
    check("done carries the understanding", done["understanding"]["language"] == "hi")
    check("streamed tokens are metered from the provider's final usage chunk",
          done["usage"]["completion_tokens"] >= 12 and done["usage"]["estimated"] is False, done["usage"])
else:
    check("stream produced agents to answer from", False, names)


# ── live evaluation against the configured model (opt-in) ───────────────────

if os.getenv("FARMXPERT_LIVE_EVAL") == "1" and llm.available():
    async def live():
        rows = []
        for case in EVAL["cases"]:
            u = await llm.understand(case["text"], case.get("hint"))
            rows.append((case, u))
        return rows
    rows = asyncio.run(live())
    per_language = {}
    for case, u in rows:
        ok = (u["language"] == case["language"]
              and (u["intent"].value if hasattr(u["intent"], "value") else u["intent"]) == case["intent"]
              and (case["crop"] is None or (u["crop"] or "").startswith(case["crop"].split()[0])))
        per_language.setdefault(case["language"], []).append(ok)
        if not ok:
            print("   live miss:", case["text"], "->", {k: u.get(k) for k in ("intent", "crop", "language")})
    accuracy = sum(sum(v) for v in per_language.values()) / len(rows)
    print("   live accuracy by language:", {k: f"{sum(v)}/{len(v)}" for k, v in per_language.items()})
    check("live: at least 90% of questions fully understood", accuracy >= 0.9, f"{accuracy:.0%}")


if __name__ == "__main__":
    print(f"\n{len(PASSED)}/{len(PASSED) + len(FAILED)} checks passed\n")
    for failure in FAILED:
        print("  FAIL", failure)
    sys.exit(1 if FAILED else 0)
