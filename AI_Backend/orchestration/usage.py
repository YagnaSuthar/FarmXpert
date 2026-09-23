"""
Token usage metering
====================
Counts every language-model and embedding token spent on one request, so the
Node backend can bill, rate-limit and report usage per farmer.

How it works: `OrchestrationService.run` opens a `UsageMeter` in a context
variable. `llm.complete` and `llm.embed` record into whatever meter is
current. asyncio copies context into every task it creates, so agents running
concurrently (the retrieval agent's query rewrite and embedding, for example)
all land on the request's meter without any of them being passed it.

Counts come from the provider's `usage` block, which is what is billed. Only
when a provider omits it is the count estimated (see `count_tokens`), and the
record says so: an estimate is never reported as a measurement.
"""

from __future__ import annotations

import contextvars
import re
import threading
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

_CURRENT: contextvars.ContextVar[Optional["UsageMeter"]] = contextvars.ContextVar(
    "farmxpert_usage_meter", default=None)


@dataclass
class UsageRecord:
    model: str
    purpose: str            # "chat" | "embedding" | "transcription" | "speech"
    prompt_tokens: int
    completion_tokens: int
    estimated: bool
    audio_seconds: float = 0.0   # speech-to-text is billed by audio length
    characters: int = 0          # text-to-speech is billed by characters


@dataclass
class UsageMeter:
    records: List[UsageRecord] = field(default_factory=list)
    # Records may arrive from worker threads (asyncio.to_thread keeps context).
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def add(self, record: UsageRecord) -> None:
        with self._lock:
            self.records.append(record)

    def summary(self) -> Dict[str, Any]:
        """Totals plus a per-model breakdown, in the response's `usage` shape."""
        by_model: Dict[str, Dict[str, Any]] = {}
        for r in self.records:
            m = by_model.setdefault(r.model, {
                "model": r.model, "purpose": r.purpose, "calls": 0,
                "prompt_tokens": 0, "completion_tokens": 0, "estimated": False,
                "audio_seconds": 0.0, "characters": 0})
            m["calls"] += 1
            m["prompt_tokens"] += r.prompt_tokens
            m["completion_tokens"] += r.completion_tokens
            m["audio_seconds"] = round(m["audio_seconds"] + r.audio_seconds, 2)
            m["characters"] += r.characters
            m["estimated"] = m["estimated"] or r.estimated
        prompt = sum(r.prompt_tokens for r in self.records)
        completion = sum(r.completion_tokens for r in self.records)
        return {
            "prompt_tokens": prompt,
            "completion_tokens": completion,
            "total_tokens": prompt + completion,
            "calls": len(self.records),
            "estimated": any(r.estimated for r in self.records),
            "audio_seconds": round(sum(r.audio_seconds for r in self.records), 2),
            "characters": sum(r.characters for r in self.records),
            "by_model": sorted(by_model.values(), key=lambda m: m["model"]),
        }


def start() -> tuple:
    """Open a meter for the current request. Returns (meter, token) for `stop`."""
    meter = UsageMeter()
    return meter, _CURRENT.set(meter)


def stop(token: contextvars.Token) -> None:
    _CURRENT.reset(token)


def record(model: str, purpose: str, provider_usage: Optional[Dict[str, Any]], *,
           prompt_text: str = "", completion_text: str = "") -> None:
    """Record one provider call on the current meter (no-op outside a request)."""
    meter = _CURRENT.get()
    if meter is None:
        return
    prompt, completion, estimated = _counts(provider_usage, prompt_text, completion_text)
    meter.add(UsageRecord(model=model, purpose=purpose, prompt_tokens=prompt,
                          completion_tokens=completion, estimated=estimated))


def record_media(model: str, purpose: str, *, audio_seconds: float = 0.0, characters: int = 0,
                 provider_usage: Optional[Dict[str, Any]] = None, estimated: bool = False) -> None:
    """Record a speech call. Tokens are recorded too when the provider reports them
    (some transcription models bill audio as input tokens)."""
    meter = _CURRENT.get()
    if meter is None:
        return
    prompt = completion = 0
    if isinstance(provider_usage, dict):
        prompt = _int(provider_usage.get("input_tokens") or provider_usage.get("prompt_tokens")) or 0
        completion = _int(provider_usage.get("output_tokens")
                          or provider_usage.get("completion_tokens")) or 0
    meter.add(UsageRecord(model=model, purpose=purpose, prompt_tokens=prompt,
                          completion_tokens=completion, estimated=estimated,
                          audio_seconds=max(0.0, float(audio_seconds)),
                          characters=max(0, int(characters))))


def _counts(usage: Optional[Dict[str, Any]], prompt_text: str,
            completion_text: str) -> tuple:
    if isinstance(usage, dict):
        prompt = _int(usage.get("prompt_tokens"))
        completion = _int(usage.get("completion_tokens"))
        total = _int(usage.get("total_tokens"))
        if prompt is not None:
            if completion is None:
                # Embedding responses carry prompt and total only.
                completion = max(0, (total or prompt) - prompt)
            return prompt, completion, False
    return count_tokens(prompt_text), count_tokens(completion_text), True


def _int(value: Any) -> Optional[int]:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return None
    return n if n >= 0 else None


# ── tokenizer ───────────────────────────────────────────────────────────────
#
# Used only when the provider does not report usage, and for prompt budgets.
# `len(text) // 4` is right for English and badly wrong for Indian scripts:
# Llama-3-class tokenizers spend roughly one token per 1-2 characters of
# Devanagari, Gujarati or Tamil, because those scripts are rare in their
# vocabularies. A farmer writing in Hindi would be under-counted 2-3x, so
# text is counted per script instead. If `tiktoken` is installed its o200k
# encoding (close to Llama 3's) is used for Latin text.

_INDIC = re.compile(r"[ऀ-෿]+")       # Devanagari .. Sinhala blocks
_CJK = re.compile(r"[぀-ヿ㐀-鿿가-힯]+")
_WS = re.compile(r"\s+")

try:  # optional, exact-ish for Latin text
    import tiktoken  # type: ignore
    _ENC = tiktoken.get_encoding("o200k_base")
except Exception:  # pragma: no cover - absent or offline
    _ENC = None


def count_tokens(text: str) -> int:
    """Estimated token count of `text` for a Llama-3-class model."""
    if not text:
        return 0
    indic = sum(len(m) for m in _INDIC.findall(text))
    cjk = sum(len(m) for m in _CJK.findall(text))
    rest = _CJK.sub(" ", _INDIC.sub(" ", text))
    if _ENC is not None:
        latin = len(_ENC.encode(rest, disallowed_special=()))
    else:
        latin = (len(_WS.sub(" ", rest).strip()) + 3) // 4
    # ~1.6 characters per token for Indic scripts, ~1 for CJK.
    return max(1, latin + round(indic / 1.6) + cjk)
