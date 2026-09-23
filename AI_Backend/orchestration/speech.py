"""
Speech: speech-to-text in, text-to-speech out
=============================================
Voice is a front door to the same orchestrator, never a second brain: the
transcript goes through exactly the same understanding and agents as typed
text, and the spoken answer is the same checked answer, read aloud.

    audio -> transcribe() -> orchestrator (mode="voice") -> SentenceSpeaker
                                                            -> synthesize() per sentence

Latency: the answer streams, and each complete sentence is sent to
text-to-speech while the model is still writing the next one. Sentences are
synthesised concurrently (bounded) and released strictly in order, so the
farmer hears the first sentence ~0.5 s after it is written.

Privacy: audio is handled in memory only. Nothing here writes it anywhere.

Configuration (defaults to the LLM provider's endpoint and key):
    SPEECH_BASE_URL, SPEECH_API_KEY
    STT_MODEL        default gpt-4o-transcribe
    TTS_MODEL        default gpt-4o-mini-tts
    TTS_VOICE        default "alloy"; TTS_VOICES='{"hi":"...","ta":"..."}' per language
    TTS_FORMAT       mp3 (default; plays everywhere) | opus | aac
    VOICE_MAX_BYTES  default 2 MB;  VOICE_MAX_SECONDS default 60
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import re
from typing import AsyncIterator, Dict, List, Optional, Tuple

import httpx

from AI_Backend.orchestration import languages, usage

logger = logging.getLogger("farmxpert.orchestration.speech")


class SpeechError(RuntimeError):
    """A speech failure the farmer should be told about, with a stable code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


# ── configuration ───────────────────────────────────────────────────────────

def _cfg() -> Dict[str, object]:
    from AI_Backend.orchestration import llm
    s = llm.settings()
    try:
        voices = json.loads(os.getenv("TTS_VOICES", "") or "{}")
    except ValueError:
        voices = {}
    return {
        "base_url": (os.getenv("SPEECH_BASE_URL") or s.base_url).rstrip("/"),
        "api_key": os.getenv("SPEECH_API_KEY") or s.api_key,
        "stt_model": os.getenv("STT_MODEL", "gpt-4o-transcribe"),
        "tts_model": os.getenv("TTS_MODEL", "gpt-4o-mini-tts"),
        "voice": os.getenv("TTS_VOICE", "alloy"),
        "voices": voices if isinstance(voices, dict) else {},
        "format": os.getenv("TTS_FORMAT", "mp3"),
        "max_bytes": int(os.getenv("VOICE_MAX_BYTES", str(2 * 1024 * 1024))),
        "max_seconds": float(os.getenv("VOICE_MAX_SECONDS", "60")),
        "timeout_s": float(os.getenv("SPEECH_TIMEOUT_S", "15")),
    }


def available() -> bool:
    return bool(_cfg()["api_key"])


# ── input audio ─────────────────────────────────────────────────────────────

def sniff(audio: bytes) -> Optional[Tuple[str, str]]:
    """(mime, extension) of a supported container, or None.

    By magic bytes: the declared type is not trusted, and a mislabelled upload
    is rejected before it costs a provider call.
    """
    head = audio[:16]
    if head.startswith(b"\x1a\x45\xdf\xa3"):
        return "audio/webm", "webm"
    if head.startswith(b"OggS"):
        return "audio/ogg", "ogg"
    if head[4:8] == b"ftyp":
        return "audio/mp4", "m4a"
    if head.startswith(b"RIFF") and head[8:12] == b"WAVE":
        return "audio/wav", "wav"
    if head.startswith(b"ID3") or (len(head) > 1 and head[0] == 0xFF and head[1] & 0xE0 == 0xE0):
        return "audio/mpeg", "mp3"
    return None


def validate_audio(audio: bytes, audio_seconds: Optional[float]) -> Tuple[str, str, float, bool]:
    """Check an upload. Returns (mime, extension, seconds, seconds_estimated)."""
    cfg = _cfg()
    if not audio:
        raise SpeechError("empty_audio", "No audio was received.")
    if len(audio) > int(cfg["max_bytes"]):
        raise SpeechError("audio_too_large", "The recording is too long. Please keep it under a minute.")
    kind = sniff(audio)
    if kind is None:
        raise SpeechError("unsupported_audio", "This audio format is not supported.")
    if audio_seconds is not None and 0 < audio_seconds <= float(cfg["max_seconds"]):
        return kind[0], kind[1], float(audio_seconds), False
    if audio_seconds is not None and audio_seconds > float(cfg["max_seconds"]):
        raise SpeechError("audio_too_long", "The recording is too long. Please keep it under a minute.")
    # ~16 kbps Opus from the recorder: 2 KB per second. Only for metering.
    return kind[0], kind[1], round(min(float(cfg["max_seconds"]), len(audio) / 2000), 2), True


async def transcribe(audio: bytes, mime: str, language_hint: Optional[str] = None, *,
                     audio_seconds: Optional[float] = None) -> str:
    """Speech to text in the farmer's language. Raises SpeechError."""
    cfg = _cfg()
    if not cfg["api_key"]:
        raise SpeechError("speech_unavailable", "Voice is not configured.")
    real_mime, ext, seconds, estimated = validate_audio(audio, audio_seconds)
    data = {"model": str(cfg["stt_model"]), "response_format": "json"}
    code = languages.normalise_code(language_hint)
    if code and code != "en":
        # A hint, not a constraint: a farmer may still switch language.
        data["language"] = code
    from AI_Backend.orchestration import llm
    try:
        response = await llm._client().post(
            f"{cfg['base_url']}/audio/transcriptions",
            headers={"Authorization": f"Bearer {cfg['api_key']}"},
            data=data, files={"file": (f"question.{ext}", audio, real_mime)},
            timeout=float(cfg["timeout_s"]))
    except httpx.TransportError as exc:
        raise SpeechError("speech_unavailable", "Voice service unreachable.") from exc
    if response.status_code != 200:
        logger.warning("Transcription returned HTTP %s", response.status_code)
        raise SpeechError("speech_unavailable", "Voice service could not process the audio.")
    try:
        body = response.json()
    except ValueError as exc:
        raise SpeechError("speech_unavailable", "Voice service returned an unreadable reply.") from exc
    usage.record_media(str(cfg["stt_model"]), "transcription", audio_seconds=seconds,
                       provider_usage=body.get("usage"), estimated=estimated)
    text = (body.get("text") or "").strip()
    if len(re.sub(r"[\W_]+", "", text)) < 2:
        raise SpeechError("no_speech", "No speech was heard in the recording.")
    return text[:2000]


# ── output speech ───────────────────────────────────────────────────────────

async def synthesize(text: str, language: str) -> bytes:
    """Text to speech. Raises SpeechError."""
    cfg = _cfg()
    if not cfg["api_key"]:
        raise SpeechError("speech_unavailable", "Voice is not configured.")
    voices: Dict[str, str] = cfg["voices"]  # type: ignore[assignment]
    lang = languages.get(language)
    body = {
        "model": cfg["tts_model"], "input": text[:4000],
        "voice": voices.get(lang.code, cfg["voice"]),
        "response_format": cfg["format"],
        # Honoured by instruction-following TTS models, ignored by others.
        "instructions": f"Speak in {lang.name}, warmly and clearly, at a calm pace, "
                        f"like an agricultural advisor talking to a farmer.",
    }
    from AI_Backend.orchestration import llm
    try:
        response = await llm._client().post(
            f"{cfg['base_url']}/audio/speech",
            headers={"Authorization": f"Bearer {cfg['api_key']}"},
            json=body, timeout=float(cfg["timeout_s"]))
    except httpx.TransportError as exc:
        raise SpeechError("speech_unavailable", "Voice service unreachable.") from exc
    if response.status_code != 200 or not response.content:
        logger.warning("Speech synthesis returned HTTP %s", response.status_code)
        raise SpeechError("speech_unavailable", "Voice service could not speak the answer.")
    usage.record_media(str(cfg["tts_model"]), "speech", characters=len(text))
    return response.content


# Sentence ends: Latin punctuation, the Devanagari/Bengali danda (। ॥), the
# Urdu full stop (۔) and the question mark forms, followed by space or end.
_SENTENCE_END = re.compile(r"(?<=[.!?।॥۔؟])\s+|\n+")
_MIN_CHARS = 12          # merge very short sentences ("Yes."): one call per word is slow
_MAX_PARALLEL = 3


def split_sentences(text: str) -> Tuple[List[str], str]:
    """(complete sentences, unfinished remainder), short ones merged."""
    pieces = _SENTENCE_END.split(text)
    remainder = pieces.pop() if pieces else ""
    out: List[str] = []
    buffer = ""
    for piece in pieces:
        piece = piece.strip()
        if not piece:
            continue
        buffer = f"{buffer} {piece}".strip()
        if len(buffer) >= _MIN_CHARS:
            out.append(buffer)
            buffer = ""
    if buffer:
        remainder = f"{buffer} {remainder}".strip()
    return out, remainder


class SentenceSpeaker:
    """Turns a stream of answer text into ordered audio clips.

    feed() text as it arrives; ready() returns clips that are finished and next
    in order (never blocks); close() then drain() for the rest. A sentence that
    fails to synthesise is skipped - the farmer still has the text - and the
    order of the others is kept.
    """

    def __init__(self, language_hint: Optional[str] = None) -> None:
        self.language = languages.normalise_code(language_hint) or "en"
        self._text = ""
        self._seq = 0
        self._next_out = 0
        self._tasks: Dict[int, Tuple[str, "asyncio.Task[bytes]"]] = {}
        self._gate = asyncio.Semaphore(_MAX_PARALLEL)
        self.spoke = False

    def feed(self, piece: str) -> None:
        self._text += piece
        sentences, self._text = split_sentences(self._text)
        for sentence in sentences:
            self._start(sentence)

    def close(self) -> None:
        tail = self._text.strip()
        self._text = ""
        if tail:
            self._start(tail)

    def _start(self, sentence: str) -> None:
        async def run() -> bytes:
            async with self._gate:
                return await synthesize(sentence, self.language)
        self._tasks[self._seq] = (sentence, asyncio.ensure_future(run()))
        self._seq += 1

    def ready(self) -> List[Dict[str, object]]:
        out = []
        while self._next_out in self._tasks and self._tasks[self._next_out][1].done():
            clip = self._release(self._next_out)
            if clip:
                out.append(clip)
        return out

    async def drain(self) -> AsyncIterator[Dict[str, object]]:
        while self._next_out < self._seq:
            _, task = self._tasks[self._next_out]
            try:
                await task
            except Exception:  # noqa: BLE001 - handled in _release
                pass
            clip = self._release(self._next_out)
            if clip:
                yield clip

    def _release(self, seq: int) -> Optional[Dict[str, object]]:
        sentence, task = self._tasks.pop(seq)
        self._next_out = seq + 1
        try:
            audio = task.result()
        except Exception as exc:  # noqa: BLE001 - one lost sentence, not a lost answer
            logger.info("Sentence %d not spoken: %s", seq, exc)
            return None
        self.spoke = True
        return {"seq": seq, "format": _cfg()["format"], "text": sentence,
                "data": base64.b64encode(audio).decode("ascii")}

    def cancel(self) -> None:
        for _, task in self._tasks.values():
            task.cancel()
