// ============================================================
// FILE: src/services/api.js
//
// Streaming questions to FarmXpert (typed and spoken).
//
// Answers stream as server-sent events over a POST, which the
// browser's EventSource cannot send - so the stream is read with
// fetch() and parsed here. Events, in order:
//   conversation -> (transcript) -> meta -> delta... -> (audio...) -> done
//   error ends a stream early with a stable `code`.
// Auth and the silent token refresh come from lib/api.js.
// ============================================================

import { ApiError, api } from '@/lib/api';

export { ApiError };

/** Parse an SSE body, calling onEvent(name, data) for each event. */
async function readEvents(response, onEvent) {
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let end;
    while ((end = buffer.search(/\r?\n\r?\n/)) !== -1) {
      const rawEvent = buffer.slice(0, end);
      buffer = buffer.slice(end).replace(/^\r?\n\r?\n/, '');
      let event = 'message';
      const data = [];
      for (const line of rawEvent.split(/\r?\n/)) {
        if (line.startsWith('event:')) event = line.slice(6).trim();
        else if (line.startsWith('data:')) data.push(line.slice(5).replace(/^ /, ''));
      }
      if (!data.length) continue;           // keep-alive comments
      let parsed = null;
      try {
        parsed = JSON.parse(data.join('\n'));
      } catch {
        continue;
      }
      onEvent(event, parsed);
    }
  }
}

async function stream(path, init, onEvent) {
  const response = await api(path, { ...init, raw: true, headers: { Accept: 'text/event-stream', ...(init.headers || {}) } });
  // Refusals (quota, validation) arrive before the stream as normal JSON.
  if (!response.ok || !response.headers.get('content-type')?.includes('text/event-stream')) {
    let body = null;
    try {
      body = await response.json();
    } catch {
      /* not JSON */
    }
    throw new ApiError(response.status, body?.error?.code || 'request_failed',
      body?.error?.message || 'Request failed', body?.error?.details);
  }
  await readEvents(response, onEvent);
}

/** A typed question, answered as a stream. */
export function askText({ query, farmId, fieldId, conversationId, language, intents, agents }, onEvent, signal) {
  return stream('/chat/ask', {
    method: 'POST',
    signal,
    body: {
      query,
      stream: true,
      ...(farmId && { farm_id: farmId }),
      ...(fieldId && { field_id: fieldId }),
      ...(conversationId && { conversation_id: conversationId }),
      ...(language && { language }),
      ...(intents?.length && { intents }),
      ...(agents?.length && { agents }),
    },
  }, onEvent);
}

/** A spoken question: the recording is the body, the ids go in the query string. */
export function askVoice(recording, { farmId, fieldId, conversationId, language }, onEvent, signal) {
  const params = new URLSearchParams();
  if (farmId) params.set('farm_id', farmId);
  if (fieldId) params.set('field_id', fieldId);
  if (conversationId) params.set('conversation_id', conversationId);
  if (language) params.set('language', language);
  if (recording.seconds) params.set('audio_seconds', recording.seconds.toFixed(2));
  // The MIME without codec parameters: `audio/webm;codecs=opus` -> `audio/webm`.
  const blob = new Blob([recording.blob], { type: recording.blob.type.split(';')[0] || 'audio/webm' });
  return stream(`/voice/ask?${params}`, {
    method: 'POST',
    signal,
    headers: { 'Content-Type': blob.type },
    body: blob,
  }, onEvent);
}
