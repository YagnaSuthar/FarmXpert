"""Provider-neutral LLM client: request shapes, fallback, settings.

    python -m AI_Backend.tests.test_llm_providers
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from contextlib import contextmanager

import httpx

from AI_Backend.orchestration import llm

PASSED, FAILED = [], []
_KEYS = ("LLM_BASE_URL", "LLM_API_KEY", "LLM_PROVIDER", "LLM_MODEL_UNDERSTAND", "LLM_MODEL_ANSWER",
         "LLM_MODEL_FALLBACK", "LLM_REASONING_UNDERSTAND", "LLM_REASONING_ANSWER", "EMBED_MODEL",
         "EMBED_DIM", "NVIDIA_API_KEY", "NVIDIA_BASE_URL", "NVIDIA_MODEL", "NVIDIA_EMBED_MODEL",
         "NVIDIA_TIMEOUT_S", "LLM_TIMEOUT_ANSWER_S", "FARMXPERT_RAG_DIM")


def check(name, ok, detail=""):
    (PASSED if ok else FAILED).append(name if ok else f"{name} -> {detail}")
    print(("  [PASS] " if ok else "  [FAIL] ") + name + ("" if ok else f"  ({detail})"))


@contextmanager
def env(**values):
    saved = {k: os.environ.pop(k, None) for k in _KEYS}
    os.environ.update({k: str(v) for k, v in values.items()})
    try:
        yield
    finally:
        for k in _KEYS:
            os.environ.pop(k, None)
        os.environ.update({k: v for k, v in saved.items() if v is not None})


OPENAI = dict(LLM_BASE_URL="https://api.openai.com/v1", LLM_API_KEY="sk-test",
              LLM_MODEL_UNDERSTAND="gpt-5-nano", LLM_MODEL_ANSWER="gpt-5", EMBED_DIM="1024")


# ── settings ────────────────────────────────────────────────────────────────

with env(**OPENAI):
    s = llm.settings()
    check("provider detected from the URL", s.provider == "openai", s.provider)
    check("openai defaults to a multilingual embedding model", s.embed_model == "text-embedding-3-small")
    check("reasoning defaults: minimal to understand, low to answer",
          (s.reasoning_understand, s.reasoning_answer) == ("minimal", "low"))

with env(NVIDIA_API_KEY="nv", NVIDIA_MODEL="meta/llama-3.3-70b-instruct", NVIDIA_TIMEOUT_S="9"):
    s = llm.settings()
    check("old NVIDIA_* settings keep working",
          (s.provider, s.api_key, s.model_answer, s.model_understand, s.timeout_answer_s)
          == ("nvidia", "nv", "meta/llama-3.3-70b-instruct", "meta/llama-3.3-70b-instruct", 9.0), s)

with env(LLM_API_KEY="k", LLM_REASONING_ANSWER="turbo"):
    check("an unknown effort falls back to low", llm.settings().reasoning_answer == "low")

with env():
    check("no key -> not available", llm.available() is False)


# ── request shape per model family ──────────────────────────────────────────

p = llm.chat_payload("s", "u", model="gpt-5", temperature=0.3, max_tokens=500, reasoning="low")
check("reasoning model: no temperature, no max_tokens",
      "temperature" not in p and "max_tokens" not in p, p)
check("reasoning model: completion budget covers hidden reasoning",
      p["max_completion_tokens"] == 500 + 1024 and p["reasoning_effort"] == "low", p)
check("o-series and namespaced names count as reasoning models",
      llm.is_reasoning_model("o4-mini") and llm.is_reasoning_model("openai/gpt-5-mini")
      and not llm.is_reasoning_model("meta/llama-3.3-70b-instruct"))
p = llm.chat_payload("s", "u", model="meta/llama-3.3-70b-instruct", temperature=0.3,
                     max_tokens=500, reasoning="low")
check("classic model: temperature and max_tokens, no reasoning",
      (p["temperature"], p["max_tokens"]) == (0.3, 500) and "reasoning_effort" not in p, p)


# ── over the wire, with a recording fake provider ──────────────────────────

class Provider:
    def __init__(self, fail_models=(), empty_models=(), dim=1024):
        self.requests = []
        self.fail_models, self.empty_models, self.dim = set(fail_models), set(empty_models), dim

    def __call__(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        self.requests.append((request.url.path, body))
        if request.url.path.endswith("/embeddings"):
            return httpx.Response(200, json={"data": [{"embedding": [0.1] * self.dim} for _ in body["input"]],
                                             "usage": {"prompt_tokens": 3, "total_tokens": 3}})
        if body["model"] in self.fail_models:
            return httpx.Response(503)
        if body["model"] in self.empty_models:
            return httpx.Response(200, json={"choices": [{"message": {"content": ""}, "finish_reason": "length"}]})
        return httpx.Response(200, json={"model": body["model"],
                                         "choices": [{"message": {"content": "ok " + body["model"]}}]})


def run(provider, coro_factory):
    async def go():
        loop = asyncio.get_running_loop()
        llm._CLIENTS[loop] = httpx.AsyncClient(transport=httpx.MockTransport(provider))
        try:
            return await coro_factory()
        finally:
            await llm._CLIENTS.pop(loop).aclose()
    return asyncio.run(go())


def outcome(coro_factory):
    async def wrapped():
        try:
            return await coro_factory()
        except llm.LLMUnavailable as exc:
            return exc
    return wrapped


with env(**OPENAI):
    fake = Provider()
    run(fake, lambda: llm.complete("s", "u", purpose="understand"))
    run(fake, lambda: llm.complete("s", "u", purpose="answer"))
    models = [b["model"] for _, b in fake.requests]
    check("each purpose uses its own model", models == ["gpt-5-nano", "gpt-5"], models)
    check("understanding runs at minimal effort", fake.requests[0][1]["reasoning_effort"] == "minimal")

    fake = Provider()
    run(fake, lambda: llm.embed(["मेरी फसल"], input_type="query"))
    body = fake.requests[0][1]
    check("openai embeddings: dimensions sent, input_type not sent",
          body.get("dimensions") == 1024 and "input_type" not in body, body)

    result = run(Provider(dim=1536), outcome(lambda: llm.embed(["x"])))
    check("a vector of the wrong width is refused", isinstance(result, llm.LLMUnavailable), result)

    result = run(Provider(empty_models={"gpt-5"}), outcome(lambda: llm.complete("s", "u")))
    check("a reasoning model that spent its budget thinking is an error, not an empty answer",
          isinstance(result, llm.LLMUnavailable), result)

with env(**OPENAI, LLM_MODEL_FALLBACK="gpt-5-mini"):
    fake = Provider(fail_models={"gpt-5"})
    answer = run(fake, lambda: llm.complete("s", "u", purpose="answer"))
    check("a failed answer retries once on the fallback model",
          answer == "ok gpt-5-mini" and [b["model"] for _, b in fake.requests] == ["gpt-5", "gpt-5-mini"],
          (answer, fake.requests))
    fake = Provider(fail_models={"gpt-5-nano"})
    result = run(fake, outcome(lambda: llm.complete("s", "u", purpose="understand")))
    check("understanding never retries: it has a safe default instead",
          isinstance(result, llm.LLMUnavailable) and len(fake.requests) == 1)

with env(NVIDIA_API_KEY="nv", EMBED_DIM="1024"):
    fake = Provider()
    run(fake, lambda: llm.embed(["x"], input_type="query"))
    body = fake.requests[0][1]
    check("nvidia embeddings: input_type sent, dimensions not sent",
          body.get("input_type") == "query" and "dimensions" not in body, body)


if __name__ == "__main__":
    print(f"\n{len(PASSED)}/{len(PASSED) + len(FAILED)} checks passed\n")
    for failure in FAILED:
        print("  FAIL", failure)
    sys.exit(1 if FAILED else 0)
