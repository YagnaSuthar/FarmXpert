/**
 * Client for the FastAPI AI backend.
 *
 * Node's built-in fetch (undici) keeps connections alive and pools them, so
 * a request reuses a warm socket instead of paying a TCP handshake. Every
 * call carries the shared internal key and a hard timeout; a refused or reset
 * connection (the AI service restarting) is retried once, anything else is
 * not - a slow agent run must not be started twice.
 */

import { config } from '../config/env.js';
import { HttpError, unavailable } from '../lib/errors.js';
import { logger } from '../lib/logger.js';

const RETRYABLE = new Set(['ECONNREFUSED', 'ECONNRESET', 'UND_ERR_SOCKET', 'EPIPE']);

function headers(requestId) {
  const out = { 'content-type': 'application/json', accept: 'application/json' };
  if (config.ai.internalKey) out['x-internal-key'] = config.ai.internalKey;
  if (requestId) out['x-request-id'] = requestId;
  return out;
}

async function call(method, path, { body, requestId, timeoutMs = config.ai.timeoutMs } = {}) {
  const url = `${config.ai.url}${path}`;
  for (let attempt = 1; ; attempt += 1) {
    try {
      const response = await fetch(url, {
        method,
        headers: headers(requestId),
        body: body === undefined ? undefined : JSON.stringify(body),
        signal: AbortSignal.timeout(timeoutMs),
      });
      const text = await response.text();
      const data = text ? safeJson(text) : null;
      // 422 is the orchestrator's own validation answer: a result, not a fault.
      if (response.ok || response.status === 422) return { status: response.status, data };
      logger.warn({ path, status: response.status }, 'AI backend returned an error');
      throw new HttpError(502, 'ai_error', 'The advisory service could not answer right now.');
    } catch (err) {
      if (err instanceof HttpError) throw err;
      if (err?.name === 'TimeoutError') {
        throw new HttpError(504, 'ai_timeout', 'The advisory service took too long to answer.');
      }
      const code = err?.cause?.code || err?.code;
      if (attempt === 1 && RETRYABLE.has(code)) continue;
      logger.error({ err, path }, 'AI backend unreachable');
      throw unavailable('The advisory service is unavailable.');
    }
  }
}

function safeJson(text) {
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

/**
 * POST and read the reply as server-sent events. Yields { event, data } with
 * data already parsed. `signal` aborts the upstream call - pass the farmer's
 * connection, so a closed app stops the model (and its bill) at once.
 */
async function* stream(path, { body, form, requestId, signal, timeoutMs = config.ai.streamTimeoutMs } = {}) {
  const h = headers(requestId);
  if (form) delete h['content-type'];          // fetch sets the multipart boundary
  h.accept = 'text/event-stream';
  const signals = [AbortSignal.timeout(timeoutMs), signal].filter(Boolean);
  let response;
  try {
    response = await fetch(`${config.ai.url}${path}`, {
      method: 'POST',
      headers: h,
      body: form ?? JSON.stringify(body),
      signal: signals.length > 1 ? AbortSignal.any(signals) : signals[0],
    });
  } catch (err) {
    if (err?.name === 'TimeoutError') {
      throw new HttpError(504, 'ai_timeout', 'The advisory service took too long to answer.');
    }
    if (err?.name === 'AbortError') throw err;
    logger.error({ err, path }, 'AI backend unreachable');
    throw unavailable('The advisory service is unavailable.');
  }
  if (response.status === 422) {
    const detail = safeJson(await response.text());
    throw new HttpError(422, 'validation_failed', 'The request could not be processed.', detail?.detail);
  }
  if (!response.ok || !response.body) {
    logger.warn({ path, status: response.status }, 'AI backend returned an error');
    throw new HttpError(502, 'ai_error', 'The advisory service could not answer right now.');
  }
  yield* parseSse(response.body);
}

/** Parse an SSE byte stream into { event, data } objects. Exported for tests. */
export async function* parseSse(readable) {
  const decoder = new TextDecoder();
  let buffer = '';
  for await (const chunk of readable) {
    buffer += decoder.decode(chunk, { stream: true });
    let end;
    // Events are separated by a blank line; tolerate \r\n from any proxy.
    while ((end = buffer.search(/\r?\n\r?\n/)) !== -1) {
      const raw = buffer.slice(0, end);
      buffer = buffer.slice(end).replace(/^\r?\n\r?\n/, '');
      let event = 'message';
      const data = [];
      for (const line of raw.split(/\r?\n/)) {
        if (line.startsWith('event:')) event = line.slice(6).trim();
        else if (line.startsWith('data:')) data.push(line.slice(5).replace(/^ /, ''));
      }
      if (data.length) yield { event, data: safeJson(data.join('\n')) };
    }
  }
}

export const ai = {
  execute: (request, requestId) =>
    call('POST', '/orchestrator/execute', { body: request, requestId }),
  executeStream: (request, requestId, signal) =>
    stream('/orchestrator/execute/stream', { body: request, requestId, signal }),
  voiceStream: (form, requestId, signal) =>
    stream('/orchestrator/voice/stream', { form, requestId, signal }),
  health: () => call('GET', '/orchestrator/health', { timeoutMs: 3000 }),
  agents: () => call('GET', '/orchestrator/agents', { timeoutMs: 5000 }),
};
