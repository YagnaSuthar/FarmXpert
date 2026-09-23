"""Voice: audio checks, sentence splitting, ordered speech, the full voice run.

    python -m AI_Backend.tests.test_speech
"""
from __future__ import annotations

import asyncio
import base64
import json
import os
import sys

import httpx

from AI_Backend.orchestration import llm, speech

PASSED, FAILED = [], []


def check(name, ok, detail=""):
    (PASSED if ok else FAILED).append(name if ok else f"{name} -> {detail}")
    print(("  [PASS] " if ok else "  [FAIL] ") + name + ("" if ok else f"  ({detail})"))


WEBM = b"\x1a\x45\xdf\xa3" + b"\x00" * 4000
OGG = b"OggS" + b"\x00" * 100
M4A = b"\x00\x00\x00\x20ftypM4A " + b"\x00" * 100

# ── input audio ─────────────────────────────────────────────────────────────

check("formats recognised by content, not by label",
      [speech.sniff(x)[1] for x in (WEBM, OGG, M4A)] == ["webm", "ogg", "m4a"])
check("a text file posing as audio is refused", speech.sniff(b"hello, not audio") is None)


def error_code(fn):
    try:
        fn()
    except speech.SpeechError as exc:
        return exc.code
    return None

check("empty upload refused", error_code(lambda: speech.validate_audio(b"", None)) == "empty_audio")
check("unsupported format refused", error_code(lambda: speech.validate_audio(b"x" * 50, None)) == "unsupported_audio")
check("over-long recording refused", error_code(lambda: speech.validate_audio(WEBM, 300)) == "audio_too_long")
os.environ["VOICE_MAX_BYTES"] = "1000"
check("oversized upload refused", error_code(lambda: speech.validate_audio(WEBM, None)) == "audio_too_large")
os.environ.pop("VOICE_MAX_BYTES")
mime, ext, seconds, estimated = speech.validate_audio(WEBM, None)
check("duration estimated from size when the client does not say", estimated and seconds == 2.0, seconds)
check("client-reported duration used when plausible", speech.validate_audio(WEBM, 7.5)[2:] == (7.5, False))

# ── sentences ───────────────────────────────────────────────────────────────

done, rest = speech.split_sentences("आज सिंचाई न करें। कल बारिश की संभावना है। खेत में")
check("Hindi danda ends a sentence", done == ["आज सिंचाई न करें।", "कल बारिश की संभावना है।"], done)
check("the unfinished tail waits for more text", rest == "खेत में", rest)
done, rest = speech.split_sentences("Yes. Ok. Water 25 millimetre today. ")
check("very short sentences are merged into one speech call",
      done == ["Yes. Ok. Water 25 millimetre today."], done)
check("decimals do not split a sentence", speech.split_sentences("pH is 8.2 today")[0] == [])

# ── ordered speech ──────────────────────────────────────────────────────────

calls = []


async def fake_synthesize(text, language):
    calls.append((text, language))
    # Later sentences finish first: order must still hold.
    await asyncio.sleep(0.05 if "first" in text else 0.001)
    if "broken" in text:
        raise speech.SpeechError("speech_unavailable", "boom")
    return f"AUDIO:{text}".encode()


RELEASED_EARLY = []


async def speak(pieces, gap=0.0):
    original = speech.synthesize
    speech.synthesize = fake_synthesize
    try:
        speaker = speech.SentenceSpeaker("hi")
        clips = []
        for piece in pieces:
            speaker.feed(piece)
            early = speaker.ready()
            RELEASED_EARLY.extend(early)
            clips += early
            # The model writes at roughly this pace; speech runs meanwhile.
            await asyncio.sleep(gap)
        speaker.close()
        async for clip in speaker.drain():
            clips.append(clip)
        return clips
    finally:
        speech.synthesize = original

clips = asyncio.run(speak(["The first sentence is slow. ", "The second one is ",
                           "fast. This broken one fails. ", "And the last words"], gap=0.06))
texts = [c["text"] for c in clips]
check("clips come out in sentence order although they finished out of order",
      texts == ["The first sentence is slow.", "The second one is fast.", "And the last words"], texts)
check("a failed sentence is skipped, the rest still spoken", len(clips) == 3)
check("clips are base64 audio with a sequence number",
      base64.b64decode(clips[0]["data"]).startswith(b"AUDIO:") and [c["seq"] for c in clips] == [0, 1, 3])
check("speech uses the farmer's language", all(lang == "hi" for _, lang in calls))
check("a finished sentence is released while later text is still arriving",
      bool(RELEASED_EARLY) and RELEASED_EARLY[0]["seq"] == 0, RELEASED_EARLY)


# ── the full voice run, with a fake provider ────────────────────────────────

def provider(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if path.endswith("/audio/transcriptions"):
        return httpx.Response(200, json={"text": "मल्चिंग क्या होती है?",
                                         "usage": {"input_tokens": 60, "output_tokens": 9}})
    if path.endswith("/audio/speech"):
        return httpx.Response(200, content=b"ID3-fake-mp3")
    body = json.loads(request.content)
    if not body.get("stream"):
        return httpx.Response(200, json={"choices": [{"message": {"content":
            '{"intent":"ask","language":"hi","query_en":"What is mulching?","confidence":0.9}'}}],
            "usage": {"prompt_tokens": 40, "completion_tokens": 15}})
    text = "मल्चिंग से मिट्टी की नमी बचती है। इससे खरपतवार भी कम होते हैं।"
    lines = [f'data: {json.dumps({"choices": [{"delta": {"content": w + " "}}]})}' for w in text.split()]
    lines += ['data: {"choices": [], "usage": {"prompt_tokens": 300, "completion_tokens": 20}}', "data: [DONE]"]
    return httpx.Response(200, text="\n\n".join(lines) + "\n\n", headers={"content-type": "text/event-stream"})


async def voice_run(audio):
    from AI_Backend.orchestration.agents import register_all
    from AI_Backend.orchestration.schemas import OrchestrationRequest
    from AI_Backend.orchestration.service import OrchestratorService
    register_all()
    loop = asyncio.get_running_loop()
    llm._CLIENTS[loop] = httpx.AsyncClient(transport=httpx.MockTransport(provider))
    events = []
    try:
        async for name, payload in OrchestratorService().stream_voice(
                audio, "audio/webm", OrchestrationRequest(query="placeholder", language="hi"),
                audio_seconds=4.0):
            events.append((name, payload))
    finally:
        await llm._CLIENTS.pop(loop).aclose()
    return events

saved = {k: os.environ.get(k) for k in ("LLM_API_KEY", "LLM_BASE_URL")}
os.environ.update(LLM_API_KEY="k", LLM_BASE_URL="https://api.openai.com/v1")
try:
    events = asyncio.run(voice_run(WEBM))
finally:
    for k, v in saved.items():
        os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)

names = [n for n, _ in events]
check("voice events: transcript first, done last",
      names[0] == "transcript" and names[-1] == "done", names)
check("the transcript, not the placeholder, is the question",
      events[0][1]["text"] == "मल्चिंग क्या होती है?")
audio_events = [p for n, p in events if n == "audio"]
check("the answer is spoken sentence by sentence",
      len(audio_events) == 2 and audio_events[0]["text"].endswith("।"), [a["text"] for a in audio_events])
done = events[-1][1]
by_purpose = {m["purpose"]: m for m in done["usage"]["by_model"]}
check("usage covers transcription, answer and speech",
      {"transcription", "chat", "speech"} <= set(by_purpose), list(by_purpose))
check("speech is metered in audio seconds and characters",
      by_purpose["transcription"]["audio_seconds"] == 4.0 and by_purpose["speech"]["characters"] > 20,
      (by_purpose.get("transcription"), by_purpose.get("speech")))
check("done carries the transcript and the voice-mode answer",
      done["transcript"] and done["answer"] and done["understanding"]["language"] == "hi")


if __name__ == "__main__":
    print(f"\n{len(PASSED)}/{len(PASSED) + len(FAILED)} checks passed\n")
    for failure in FAILED:
        print("  FAIL", failure)
    sys.exit(1 if FAILED else 0)
