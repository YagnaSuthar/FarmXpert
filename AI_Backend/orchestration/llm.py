"""
Language model client (OpenAI-compatible: OpenAI, NVIDIA, others)
==================================================================
The LLM is used at exactly two edges and never in the middle:

  1. understanding  - a farmer's free-text question becomes one of the closed
                      intents in planner.Intent. The model's answer is matched
                      against that list; anything else falls back to ASK. It
                      can never name an agent or cause one to execute.
  2. explaining     - validated agent output becomes a paragraph in the
                      farmer's language. Numbers are passed through, never
                      recomputed, and the model is told so explicitly.

Everything between those two edges - selection, ordering, timeouts, retries,
safety rules - is deterministic Python, because that is the part that has to
be provably correct.

Configuration (environment, never hardcoded; read on every call, so a
deployment can be re-pointed without code changes):

    LLM_BASE_URL          any OpenAI-compatible endpoint, e.g. https://api.openai.com/v1
    LLM_API_KEY           required to enable the LLM at all
    LLM_PROVIDER          openai | nvidia | compatible  (default: from the URL)
    LLM_MODEL_UNDERSTAND  classifying the question  - a small, fast model
    LLM_MODEL_ANSWER      writing the answer        - the quality model
    LLM_MODEL_FALLBACK    one retry when the answer model fails or is too slow
    LLM_REASONING_UNDERSTAND / LLM_REASONING_ANSWER
                          reasoning effort for GPT-5 / o-series models
                          (minimal | low | medium | high); default minimal / low
    LLM_TIMEOUT_UNDERSTAND_S / LLM_TIMEOUT_ANSWER_S   default 6 / 20
    EMBED_MODEL, EMBED_DIM  embeddings for the knowledge index (default 1024)

The NVIDIA_* names used before (NVIDIA_API_KEY, NVIDIA_BASE_URL,
NVIDIA_MODEL, NVIDIA_EMBED_MODEL, NVIDIA_TIMEOUT_S) still work as fallbacks.

With no key configured the orchestrator degrades: structured results are still
returned, only the written answer is absent. It never fails for want of a key.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import weakref
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, AsyncIterator, Dict, List, Optional, Tuple

import httpx

from AI_Backend.orchestration import usage
from AI_Backend.orchestration.prompt_view import project
from AI_Backend.orchestration.toon import encode_agent_results, fit

logger = logging.getLogger("farmxpert.orchestration.llm")

MAX_CONTEXT_TOKENS = int(os.getenv("NVIDIA_MAX_CONTEXT_TOKENS", os.getenv("LLM_MAX_CONTEXT_TOKENS", "6000")))
_REASONING_PREFIXES = ("gpt-5", "o1", "o3", "o4")
_EFFORTS = {"minimal", "low", "medium", "high"}


def _env(*names: str, default: str = "") -> str:
    for name in names:
        value = os.getenv(name, "").strip()
        if value:
            return value
    return default


@dataclass(frozen=True)
class Settings:
    base_url: str
    api_key: str
    provider: str
    model_understand: str
    model_answer: str
    model_fallback: str
    reasoning_understand: str
    reasoning_answer: str
    timeout_understand_s: float
    timeout_answer_s: float
    embed_model: str
    embed_dim: int


def settings() -> Settings:
    base_url = _env("LLM_BASE_URL", "NVIDIA_BASE_URL",
                    default="https://integrate.api.nvidia.com/v1").rstrip("/")
    provider = _env("LLM_PROVIDER").lower() or (
        "openai" if "api.openai.com" in base_url
        else "nvidia" if "nvidia.com" in base_url else "compatible")
    answer = _env("LLM_MODEL_ANSWER", "NVIDIA_MODEL", default=(
        "gpt-5-mini" if provider == "openai" else "meta/llama-3.3-70b-instruct"))
    legacy_timeout = _env("NVIDIA_TIMEOUT_S")
    return Settings(
        base_url=base_url,
        api_key=_env("LLM_API_KEY", "NVIDIA_API_KEY"),
        provider=provider,
        model_understand=_env("LLM_MODEL_UNDERSTAND", default=answer),
        model_answer=answer,
        model_fallback=_env("LLM_MODEL_FALLBACK"),
        reasoning_understand=_effort(_env("LLM_REASONING_UNDERSTAND", default="minimal")),
        reasoning_answer=_effort(_env("LLM_REASONING_ANSWER", default="low")),
        timeout_understand_s=float(_env("LLM_TIMEOUT_UNDERSTAND_S", default=legacy_timeout or "6")),
        timeout_answer_s=float(_env("LLM_TIMEOUT_ANSWER_S", default=legacy_timeout or "20")),
        embed_model=_env("EMBED_MODEL", "NVIDIA_EMBED_MODEL", default=(
            "text-embedding-3-small" if provider == "openai" else "nvidia/nv-embedqa-e5-v5")),
        embed_dim=int(_env("EMBED_DIM", "FARMXPERT_RAG_DIM", default="1024")),
    )


def _effort(value: str) -> str:
    return value.lower() if value.lower() in _EFFORTS else "low"


def is_reasoning_model(model: str) -> bool:
    name = model.lower().rsplit("/", 1)[-1]
    return name.startswith(_REASONING_PREFIXES)


def api_key() -> str:
    return settings().api_key


def available() -> bool:
    return bool(api_key())


class LLMUnavailable(RuntimeError):
    """No key configured, or the provider could not be reached."""


# One client per event loop. A fresh AsyncClient per call throws away the
# connection pool and pays TLS setup on every request, which on a farmer-facing
# path is pure added latency. Keyed weakly so a closed loop is collected.
_CLIENTS: "weakref.WeakKeyDictionary[Any, httpx.AsyncClient]" = weakref.WeakKeyDictionary()


def _client() -> httpx.AsyncClient:
    loop = asyncio.get_running_loop()
    client = _CLIENTS.get(loop)
    if client is None or client.is_closed:
        client = httpx.AsyncClient(
            timeout=20.0, http2=_http2_available(),
            limits=httpx.Limits(max_connections=32, max_keepalive_connections=16))
        _CLIENTS[loop] = client
    return client


def _http2_available() -> bool:
    # HTTP/2 multiplexes concurrent calls on one TLS connection; it needs the
    # optional `h2` package and silently falls back to HTTP/1.1 without it.
    try:
        import h2  # noqa: F401
        return True
    except ImportError:
        return False


async def aclose_clients() -> None:
    """Close pooled clients on shutdown. Safe to call when none exist."""
    loop = asyncio.get_running_loop()
    client = _CLIENTS.pop(loop, None)
    if client is not None and not client.is_closed:
        await client.aclose()


def chat_payload(system: str, user: str, *, model: str, temperature: float,
                 max_tokens: int, reasoning: Optional[str]) -> Dict[str, Any]:
    """The request body, shaped for the model family.

    Reasoning models (GPT-5, o-series) reject `temperature` and `max_tokens`:
    they take `max_completion_tokens`, which also has to cover the hidden
    reasoning tokens, and `reasoning_effort`.
    """
    payload: Dict[str, Any] = {
        "model": model,
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": user}],
        "stream": False,
    }
    if is_reasoning_model(model):
        headroom = {"minimal": 256, "low": 1024, "medium": 4096, "high": 8192}
        effort = reasoning or "low"
        payload["max_completion_tokens"] = max_tokens + headroom.get(effort, 1024)
        payload["reasoning_effort"] = effort
    else:
        payload["temperature"] = temperature
        payload["max_tokens"] = max_tokens
    return payload


async def complete(system: str, user: str, *,
                   purpose: str = "answer",
                   temperature: float = 0.2,
                   max_tokens: int = 700,
                   model: Optional[str] = None,
                   timeout_s: Optional[float] = None) -> str:
    """One chat completion. Raises LLMUnavailable rather than a provider error.

    `purpose` picks the configured model, reasoning effort and deadline:
    "understand" (fast classification) or "answer" (quality). For "answer",
    a failure or timeout is retried once on LLM_MODEL_FALLBACK when set.
    """
    s = settings()
    if not s.api_key:
        raise LLMUnavailable("LLM_API_KEY is not configured.")
    understand = purpose == "understand"
    chosen = model or (s.model_understand if understand else s.model_answer)
    reasoning = s.reasoning_understand if understand else s.reasoning_answer
    deadline = timeout_s or (s.timeout_understand_s if understand else s.timeout_answer_s)
    try:
        return await _complete_once(s, system, user, chosen, temperature, max_tokens,
                                    reasoning, deadline)
    except LLMUnavailable as exc:
        if understand or not s.model_fallback or s.model_fallback == chosen or model:
            raise
        logger.warning("Answer model %s failed (%s); retrying on %s.", chosen, exc, s.model_fallback)
        return await _complete_once(s, system, user, s.model_fallback, temperature, max_tokens,
                                    "minimal", deadline)


async def _complete_once(s: Settings, system: str, user: str, model: str, temperature: float,
                         max_tokens: int, reasoning: str, deadline: float) -> str:
    payload = chat_payload(system, user, model=model, temperature=temperature,
                           max_tokens=max_tokens, reasoning=reasoning)
    try:
        response = await _client().post(
            f"{s.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {s.api_key}", "Accept": "application/json"},
            json=payload, timeout=deadline)
        if response.status_code != 200:
            # The body can echo request content; log the status only.
            raise LLMUnavailable(f"Model provider returned HTTP {response.status_code}.")
        data = response.json()
        if not isinstance(data, dict):
            raise ValueError("unexpected body")
        choices = data.get("choices") or [{}]
        text = ((choices[0].get("message") or {}).get("content") or "").strip()
        # A 200 is billed whether or not the reply is usable, so it is
        # recorded before the reply is checked.
        usage.record(data.get("model") or model, "chat", data.get("usage"),
                     prompt_text=system + "\n" + user, completion_text=text)
        if not choices[0].get("message"):
            raise KeyError("choices")
        if not text and choices[0].get("finish_reason") == "length":
            # A reasoning model spent the whole budget thinking.
            raise LLMUnavailable("Model used its token budget before answering.")
        return text
    except (httpx.TransportError, KeyError, IndexError, ValueError) as exc:
        raise LLMUnavailable(f"Model provider unreachable: {type(exc).__name__}") from exc


_EMBED_CACHE: "OrderedDict[tuple, tuple]" = OrderedDict()
_EMBED_CACHE_SIZE = int(os.getenv("EMBED_QUERY_CACHE_SIZE", "2048"))


async def embed(texts: List[str], *, model: Optional[str] = None,
                input_type: str = "passage") -> List[List[float]]:
    """Embeddings for the RAG index and for queries.

    NVIDIA retrieval models need `input_type` ("passage" for documents,
    "query" for questions); OpenAI rejects it but takes `dimensions`, which
    keeps its vectors at the index's width (EMBED_DIM) with no schema change.
    """
    s = settings()
    if not s.api_key:
        raise LLMUnavailable("LLM_API_KEY is not configured.")
    embed_model = model or s.embed_model
    # Farmers ask the same questions ("when to irrigate wheat") all day; a
    # repeated query skips the network round trip, and costs nothing.
    cache_key = None
    if input_type == "query":
        cache_key = (embed_model, s.embed_dim, tuple(texts))
        cached = _EMBED_CACHE.get(cache_key)
        if cached is not None:
            _EMBED_CACHE.move_to_end(cache_key)
            return [list(v) for v in cached]
    body: Dict[str, Any] = {"model": embed_model, "input": texts, "encoding_format": "float"}
    if s.provider == "nvidia":
        body["input_type"] = input_type
    elif embed_model.startswith("text-embedding-3"):
        body["dimensions"] = s.embed_dim

    try:
        response = await _client().post(
            f"{s.base_url}/embeddings",
            headers={"Authorization": f"Bearer {s.api_key}", "Accept": "application/json"},
            json=body, timeout=s.timeout_understand_s)
        if response.status_code != 200:
            raise LLMUnavailable(f"Embedding provider returned HTTP {response.status_code}.")
        data = response.json()
        usage.record(embed_model, "embedding", data.get("usage"),
                     prompt_text="\n".join(texts))
        vectors = [item["embedding"] for item in data["data"]]
        if any(len(v) != s.embed_dim for v in vectors):
            # A mismatched width would be rejected by pgvector at write time
            # or, worse, compared meaninglessly; fail here, loudly.
            raise LLMUnavailable(
                f"{embed_model} returned {len(vectors[0])}-dim vectors; the index expects {s.embed_dim}.")
        if cache_key is not None:
            _EMBED_CACHE[cache_key] = tuple(tuple(v) for v in vectors)
            while len(_EMBED_CACHE) > _EMBED_CACHE_SIZE:
                _EMBED_CACHE.popitem(last=False)
        return vectors
    except (httpx.TransportError, KeyError, ValueError, TypeError, IndexError) as exc:
        raise LLMUnavailable(f"Embedding provider unreachable: {type(exc).__name__}") from exc

# ── edge 1: understanding ───────────────────────────────────────────────────

_UNDERSTAND_SYSTEM = """You classify an Indian farmer's question for a farm advisory system.
The question may be in any Indian language, in its own script or typed in English
letters (e.g. "mera gehu sukh raha hai" is Hindi), or mix languages.

Answer with JSON only, no prose:
{"intent": "<one of: daily_plan, irrigation, crop_choice, soil, weather, market, ask>",
 "crop": "<crop name in English, or null>",
 "language": "<ISO 639-1 code of the language the farmer wrote in>",
 "query_en": "<the question faithfully translated to plain English>",
 "confidence": <0.0-1.0, how sure you are of the intent>}

Rules:
- Pick the single closest intent. A general knowledge question is "ask".
- Never invent a crop that was not mentioned. Local crop names map to English
  (gehu/gahu -> wheat, dhan/chawal -> rice, kapas -> cotton, magfali -> groundnut).
- query_en keeps every number, unit, date and place exactly as given."""


async def understand(query: str, hint_language: Optional[str] = None) -> Dict[str, Any]:
    """Free text to a constrained intent. Never returns an agent name.

    Script and, where the script decides it, language are detected
    deterministically first; the model adds intent, crop, the language for
    shared scripts and an English rendering used by search. A model that
    cannot be reached, or answers with something unexpected, yields the safe
    default rather than an error: the farmer still gets the knowledge path,
    in their own language.
    """
    from AI_Backend.orchestration import languages
    from AI_Backend.orchestration.planner import Intent

    detected = languages.detect(query, hint_language)
    result: Dict[str, Any] = {
        "intent": Intent.ASK, "crop": None, "language": detected.language,
        "script": detected.script, "query_en": query if detected.language == "en" else None,
        "confidence": None, "source": "detected",
    }
    if not available():
        return _with_tier(result)
    try:
        raw = await complete(_UNDERSTAND_SYSTEM, query, purpose="understand",
                             temperature=0.0, max_tokens=220)
        parsed = json.loads(_first_json_object(raw))
        if not isinstance(parsed, dict):
            raise ValueError("not an object")
    except (LLMUnavailable, ValueError, TypeError) as exc:
        logger.info("Intent classification unavailable (%s); defaulting to a question.", exc)
        return _with_tier(result)

    try:
        result["intent"] = Intent(str(parsed.get("intent", "")).strip().lower())
    except ValueError:
        logger.warning("Model proposed unknown intent %r; treating as a question.",
                       parsed.get("intent"))
    crop = parsed.get("crop")
    result["crop"] = str(crop).strip().lower()[:60] if crop else None
    result["language"] = languages.reconcile(parsed.get("language"), detected)
    query_en = parsed.get("query_en")
    if isinstance(query_en, str) and query_en.strip():
        result["query_en"] = query_en.strip()[:2000]
    try:
        confidence = float(parsed.get("confidence"))
        result["confidence"] = confidence if 0.0 <= confidence <= 1.0 else None
    except (TypeError, ValueError):
        pass
    result["source"] = "model"
    return _with_tier(result)


def _with_tier(result: Dict[str, Any]) -> Dict[str, Any]:
    from AI_Backend.orchestration import languages
    result["tier"] = languages.get(result["language"]).tier
    return result


# ── edge 2: explaining ──────────────────────────────────────────────────────

_ANSWER_RULES = """You are an agricultural extension officer answering one farmer.

Absolute rules:
- Use only the facts given. If something is missing, say it is not available.
- Never change a number, a dose, a depth, a date or a price. Copy them exactly.
- Never invent a recommendation the facts do not contain.
- If the facts contain a conflict or a refusal, tell the farmer about it plainly.

Style: speak to the farmer directly, in short sentences.
Lead with what to do today."""

# Typed answers are rendered as Markdown in the app, so structure helps the
# farmer scan them on a phone.
_TEXT_RULES = """This answer is READ in the app, which renders Markdown.
- Open with one bold line: the single most important action today.
- Then short bullet points; **bold** the key numbers (doses, mm, dates, prices).
- When comparing 3+ items (days of a forecast, crops, markets), use a small
  Markdown table of at most 4 columns.
- Use a `###` heading only to separate two clearly different topics.
- Keep it under 220 words. No emoji, no code blocks."""

# Voice answers are read aloud by text-to-speech: no symbols it would spell
# out, units said in words, and short enough to listen to in one go.
_VOICE_RULES = """This answer will be SPOKEN aloud to the farmer.
- At most 5 short sentences, under 80 words. The most important action first.
- No lists, bullets, tables, brackets, emoji or abbreviations.
- Write units and symbols as words (25 mm -> 25 millimetre, 30% -> 30 percent,
  Rs 2400 -> 2400 rupees), still copying every number exactly."""

_FORMAT_NOTE = {
    "json": "The FACTS are JSON produced by validated agronomic tools.",
    "toon": ("The FACTS are in TOON, a compact format: `name[count]{col1,col2}:` "
             "introduces a table and each following line is one row in that column "
             "order. `-` means no value."),
}


def build_facts(results: Dict[str, Any]) -> Tuple[str, str]:
    """The facts block for the prompt, and the format it is written in.

    Two decisions, in this order, both measured rather than assumed:

    1. PROJECT first. Agent payloads carry diagnostics, model versions and
       intermediate values that no answer depends on. On real FarmXpert
       results, projecting to the facts that matter cuts the prompt by about
       89% - far more than any choice of syntax. This is the saving that
       matters.
    2. THEN pick the cheaper encoding for THIS payload. Measured on the
       projected view, minified JSON usually beats TOON, because the view has
       little repetition left to amortise a column header over; TOON still
       wins on genuinely tabular payloads such as a multi-day forecast. So
       both are built and the smaller one is sent, which is never worse than
       committing to either.

    Length is the proxy for tokens: it needs no tokenizer dependency and the
    two correlate closely enough to pick a winner.
    """
    view = project(results)
    as_json = json.dumps(view, separators=(",", ":"), default=str, ensure_ascii=False)
    as_toon = encode_agent_results(view)
    return (as_toon, "toon") if len(as_toon) < len(as_json) else (as_json, "json")


def answer_prompt(query: Optional[str], results: Dict[str, Any], *,
                  language: str = "en", script: str = "latn", mode: str = "text",
                  conflicts: Optional[List[Dict[str, Any]]] = None,
                  warnings: Optional[List[str]] = None,
                  history: Optional[List[Dict[str, str]]] = None) -> Tuple[str, str]:
    """(system, user) for the answer. Shared by the blocking and streaming paths."""
    from AI_Backend.orchestration import languages

    facts, fact_format = build_facts(results)
    extra: Dict[str, Any] = {}
    if conflicts:
        extra["conflicts"] = [{"topic": c.get("topic"), "advice": c.get("farmer_note", "")}
                              for c in conflicts]
    if warnings:
        extra["not_available"] = list(warnings)[:4]
    if extra:
        facts += "\n" + json.dumps(extra, separators=(",", ":"), default=str,
                                   ensure_ascii=False)

    system = f"{_ANSWER_RULES}\n\n{_FORMAT_NOTE[fact_format]}"
    system += "\n\n" + (_VOICE_RULES if mode == "voice" else _TEXT_RULES)
    earlier = ""
    if history:
        # The last few turns only: enough to resolve "and tomorrow?", while the
        # prompt cost of memory stays flat instead of growing with the thread.
        lines = [f"{t['role']}: {t['content'][:400]}" for t in history[-6:]]
        earlier = "Earlier in this conversation:\n" + "\n".join(lines) + "\n\n"
    user = (earlier + f"Language: {languages.answer_instruction(language, script)}\n"
            f"Question: {query or 'What should I do on my farm now?'}\n\n"
            f"FACTS:\n{fit(facts, MAX_CONTEXT_TOKENS)}")
    return system, user


def answer_budget(mode: str) -> int:
    return 260 if mode == "voice" else 700


async def answer(query: Optional[str], results: Dict[str, Any], *,
                 language: str = "en", script: str = "latn", mode: str = "text",
                 conflicts: Optional[List[Dict[str, Any]]] = None,
                 warnings: Optional[List[str]] = None,
                 history: Optional[List[Dict[str, str]]] = None) -> Optional[str]:
    """Write the farmer-facing answer from validated results, or None.

    Returning None is a legitimate outcome: no key, no facts, or the provider
    is down. The caller still has the structured results.
    """
    if not available() or not results:
        return None
    system, prompt = answer_prompt(query, results, language=language, script=script, mode=mode,
                                   conflicts=conflicts, warnings=warnings, history=history)
    try:
        return await complete(system, prompt, purpose="answer", temperature=0.3,
                              max_tokens=answer_budget(mode))
    except LLMUnavailable as exc:
        logger.info("Farmer answer not generated (%s); returning structured results only.", exc)
        return None


async def answer_stream(query: Optional[str], results: Dict[str, Any], *,
                        language: str = "en", script: str = "latn", mode: str = "text",
                        conflicts: Optional[List[Dict[str, Any]]] = None,
                        warnings: Optional[List[str]] = None,
                        history: Optional[List[Dict[str, str]]] = None) -> AsyncIterator[str]:
    """The answer, piece by piece. Yields nothing when no answer can be written.

    A failure before the first piece is retried once on LLM_MODEL_FALLBACK; a
    failure mid-answer ends the stream with what was already sent - the caller
    still has the structured results, and a half-sentence is not repeated.
    """
    if not available() or not results:
        return
    system, prompt = answer_prompt(query, results, language=language, script=script, mode=mode,
                                   conflicts=conflicts, warnings=warnings, history=history)
    s = settings()
    models = [s.model_answer] + ([s.model_fallback] if s.model_fallback
                                 and s.model_fallback != s.model_answer else [])
    for attempt, model in enumerate(models):
        sent = False
        try:
            async for piece in stream_complete(
                    system, prompt, model=model, temperature=0.3, max_tokens=answer_budget(mode),
                    reasoning=s.reasoning_answer if attempt == 0 else "minimal",
                    deadline=s.timeout_answer_s):
                sent = True
                yield piece
            return
        except LLMUnavailable as exc:
            if sent or attempt == len(models) - 1:
                logger.info("Streamed answer ended early (%s).", exc)
                return
            logger.warning("Answer model %s failed before streaming (%s); retrying on %s.",
                           model, exc, models[attempt + 1])


async def stream_complete(system: str, user: str, *, model: str, temperature: float,
                          max_tokens: int, reasoning: str, deadline: float) -> AsyncIterator[str]:
    """One streamed chat completion (OpenAI-compatible server-sent events)."""
    s = settings()
    if not s.api_key:
        raise LLMUnavailable("LLM_API_KEY is not configured.")
    payload = chat_payload(system, user, model=model, temperature=temperature,
                           max_tokens=max_tokens, reasoning=reasoning)
    payload["stream"] = True
    if s.provider == "openai":
        # Without this OpenAI omits token counts from streamed responses.
        payload["stream_options"] = {"include_usage": True}

    text: List[str] = []
    provider_usage: Optional[Dict[str, Any]] = None
    reported_model = model
    opened = False
    try:
        async with _client().stream(
                "POST", f"{s.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {s.api_key}", "Accept": "text/event-stream"},
                json=payload, timeout=httpx.Timeout(deadline, connect=5.0)) as response:
            if response.status_code != 200:
                raise LLMUnavailable(f"Model provider returned HTTP {response.status_code}.")
            opened = True
            async for line in response.aiter_lines():
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)
                except ValueError:
                    continue
                if chunk.get("usage"):
                    provider_usage = chunk["usage"]
                reported_model = chunk.get("model") or reported_model
                for choice in chunk.get("choices") or []:
                    piece = (choice.get("delta") or {}).get("content")
                    if piece:
                        text.append(piece)
                        yield piece
    except httpx.TransportError as exc:
        raise LLMUnavailable(f"Model provider unreachable: {type(exc).__name__}") from exc
    finally:
        # Billed once the provider accepted the request, however it ended.
        if opened:
            usage.record(reported_model, "chat", provider_usage,
                         prompt_text=system + "\n" + user, completion_text="".join(text))


def _first_json_object(text: str) -> str:
    """Pull the first {...} out of a reply that may carry stray prose."""
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("no JSON object in model reply")
    return text[start:end + 1]
