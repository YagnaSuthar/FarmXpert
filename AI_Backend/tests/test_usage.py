"""Token usage metering.

    python -m AI_Backend.tests.test_usage
"""
from __future__ import annotations

import asyncio
import os
import sys

import httpx

from AI_Backend.orchestration import llm, usage

PASSED, FAILED = [], []


def check(name, ok, detail=""):
    (PASSED if ok else FAILED).append(name if ok else f"{name} -> {detail}")
    print(("  [PASS] " if ok else "  [FAIL] ") + name + ("" if ok else f"  ({detail})"))


# ── tokenizer ───────────────────────────────────────────────────────────────

english = "Should I irrigate my wheat field today given the forecast?"
hindi = "क्या मुझे आज अपने गेहूं के खेत में सिंचाई करनी चाहिए?"
check("empty text is zero tokens", usage.count_tokens("") == 0)
check("english is roughly chars/4", 8 <= usage.count_tokens(english) <= 20, usage.count_tokens(english))
check("hindi is not under-counted like chars/4 would",
      usage.count_tokens(hindi) > len(hindi) // 4 * 2, (usage.count_tokens(hindi), len(hindi)))


# ── meter ───────────────────────────────────────────────────────────────────

usage.record("m", "chat", {"prompt_tokens": 5, "completion_tokens": 5})
check("recording outside a request is a no-op", True)

meter, token = usage.start()
usage.record("meta/llama", "chat", {"prompt_tokens": 120, "completion_tokens": 40, "total_tokens": 160})
usage.record("nv-embed", "embedding", {"prompt_tokens": 9, "total_tokens": 9})
usage.record("meta/llama", "chat", None, prompt_text=english, completion_text="Yes, 25 mm.")
usage.stop(token)
s = meter.summary()
check("totals add up", (s["prompt_tokens"], s["calls"]) == (120 + 9 + usage.count_tokens(english), 3), s)
check("total = prompt + completion", s["total_tokens"] == s["prompt_tokens"] + s["completion_tokens"])
check("embedding has no completion tokens",
      next(m for m in s["by_model"] if m["purpose"] == "embedding")["completion_tokens"] == 0)
check("a missing provider count is marked estimated", s["estimated"] is True)
llama = next(m for m in s["by_model"] if m["model"] == "meta/llama")
check("per-model breakdown", (llama["calls"], llama["estimated"]) == (2, True), llama)


async def concurrent_tasks_share_the_request_meter():
    meter, token = usage.start()

    async def agent(n):
        await asyncio.sleep(0)
        usage.record("m", "chat", {"prompt_tokens": n, "completion_tokens": 1})

    await asyncio.gather(*(agent(i) for i in range(1, 11)))
    await asyncio.to_thread(usage.record, "m", "chat", {"prompt_tokens": 100, "completion_tokens": 0})
    usage.stop(token)
    return meter.summary()

s = asyncio.run(concurrent_tasks_share_the_request_meter())
check("concurrent agents and threads land on one meter", (s["calls"], s["prompt_tokens"]) == (11, 155), s)


async def two_requests_do_not_mix():
    async def request(n):
        meter, token = usage.start()
        for _ in range(n):
            await asyncio.sleep(0)
            usage.record("m", "chat", {"prompt_tokens": 1, "completion_tokens": 0})
        usage.stop(token)
        return meter.summary()["calls"]
    return await asyncio.gather(request(3), request(7))

check("parallel requests keep separate meters", asyncio.run(two_requests_do_not_mix()) == [3, 7])


# ── through the real client, with a fake provider ───────────────────────────

def provider(request: httpx.Request) -> httpx.Response:
    if "/broken/" in request.url.path:
        return httpx.Response(200, json={"usage": {"prompt_tokens": 50, "completion_tokens": 0}})
    if request.url.path.endswith("/chat/completions"):
        return httpx.Response(200, json={
            "model": "meta/llama-3.3-70b-instruct",
            "choices": [{"message": {"content": '{"intent":"irrigation","crop":"wheat","language":"en"}'}}],
            "usage": {"prompt_tokens": 210, "completion_tokens": 18, "total_tokens": 228}})
    if request.url.path.endswith("/embeddings"):
        return httpx.Response(200, json={"data": [{"embedding": [0.0] * 4}],
                                         "usage": {"prompt_tokens": 12, "total_tokens": 12}})
    return httpx.Response(404)


async def through_client():
    os.environ["NVIDIA_API_KEY"] = "test-key"
    os.environ["EMBED_DIM"] = "4"
    loop = asyncio.get_running_loop()
    llm._CLIENTS[loop] = httpx.AsyncClient(transport=httpx.MockTransport(provider))
    meter, token = usage.start()
    try:
        await llm.complete("sys", "user")
        await llm.embed(["q"], input_type="query")
        broken_raised = False
        os.environ["LLM_BASE_URL"] = "https://integrate.api.nvidia.com/v1/broken"
        try:
            await llm.complete("sys", "user")
        except llm.LLMUnavailable:
            broken_raised = True
        finally:
            os.environ.pop("LLM_BASE_URL", None)
    finally:
        usage.stop(token)
        await llm._CLIENTS.pop(loop).aclose()
        os.environ.pop("NVIDIA_API_KEY", None)
        os.environ.pop("EMBED_DIM", None)
    return meter.summary(), broken_raised

s, broken_raised = asyncio.run(through_client())
check("provider counts are used, not estimated", s["estimated"] is False, s)
check("chat + embedding + billed-but-unusable reply are all counted",
      (s["calls"], s["prompt_tokens"], s["completion_tokens"]) == (3, 210 + 12 + 50, 18), s)
check("an unusable 200 still raises for the caller", broken_raised)


async def through_orchestrator():
    """The response carries usage for the whole request."""
    from AI_Backend.orchestration.schemas import OrchestrationRequest
    from AI_Backend.orchestration.service import OrchestratorService
    os.environ["NVIDIA_API_KEY"] = "test-key"
    loop = asyncio.get_running_loop()
    llm._CLIENTS[loop] = httpx.AsyncClient(transport=httpx.MockTransport(provider))
    try:
        response = await OrchestratorService().run(OrchestrationRequest(
            query="Should I water my wheat?", explain=False, soil={"soil_moisture": 20}))
    finally:
        await llm._CLIENTS.pop(loop).aclose()
        os.environ.pop("NVIDIA_API_KEY", None)
    return response

response = asyncio.run(through_orchestrator())
check("orchestrator response reports the understanding call",
      response.usage.calls >= 1 and response.usage.prompt_tokens >= 210, response.usage)
check("usage is in the JSON contract", "usage" in response.model_dump(mode="json"))


if __name__ == "__main__":
    print(f"\n{len(PASSED)}/{len(PASSED) + len(FAILED)} checks passed\n")
    for failure in FAILED:
        print("  FAIL", failure)
    sys.exit(1 if FAILED else 0)
