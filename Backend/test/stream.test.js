// Streaming: SSE parsing, the relay to the app, and voice request checks.
// No database and no AI backend: the relay is driven by a fake event source.
process.env.LOG_LEVEL = 'silent';

const assert = (await import('node:assert/strict')).default;
const { after, before, test } = await import('node:test');
const express = (await import('express')).default;
const { parseSse } = await import('../src/clients/ai.js');
const { relay } = await import('../src/modules/chat/routes.js');
const { createApp } = await import('../src/app.js');
const { HttpError, errorHandler } = await import('../src/lib/errors.js');

async function* chunks(...parts) {
  for (const part of parts) yield new TextEncoder().encode(part);
}

async function collect(iterable) {
  const out = [];
  for await (const item of iterable) out.push(item);
  return out;
}

test('SSE parser: events split across chunks, CRLF, multi-line data', async () => {
  const events = await collect(parseSse(chunks(
    'event: meta\ndata: {"a":',
    '1}\n\nevent: delta\r\ndata: {"text":"मल्चिंग "}\r\n\r\n',
    ': keep-alive comment\n\n',
    'event: done\ndata: {"x":\ndata: 2}\n\n',
  )));
  assert.deepEqual(events, [
    { event: 'meta', data: { a: 1 } },
    { event: 'delta', data: { text: 'मल्चिंग ' } },
    { event: 'done', data: { x: 2 } },
  ]);
});

test('SSE parser: a multi-byte character split between chunks survives', async () => {
  const bytes = new TextEncoder().encode('event: delta\ndata: {"text":"गेहूं"}\n\n');
  const [event] = await collect(parseSse((async function* () {
    yield bytes.slice(0, 25);
    yield bytes.slice(25);
  })()));
  assert.equal(event.data.text, 'गेहूं');
});

// ── relay, on a real HTTP server ────────────────────────────────────────────

let server;
let base;
let lastUpstreamAborted = false;
const turn = {
  requestId: 'req-test-0001', askedAt: new Date(), started: performance.now(),
  conversation: { id: '3f2b8c1e-7d4a-4e9b-9c1a-2b3c4d5e6f70' }, farm: null, field: null,
  aiRequest: {}, language: 'hi', inputMode: 'text', body: {},
};

before(async () => {
  const app = express();
  app.post('/ok', (req, res) => relay(req, res, turn, async function* () {
    yield { event: 'meta', data: { understanding: { language: 'hi' } } };
    yield { event: 'delta', data: { text: 'पानी ' } };
    yield { event: 'delta', data: { text: 'दें।' } };
    yield { event: 'done', data: { request_id: 'req-test-0001', status: 'success', answer: 'पानी दें।',
      understanding: { language: 'hi' }, usage: { by_model: [] } } };
  }, { question: 'q' }));
  app.post('/refused', async (req, res, next) => {
    try {
      await relay(req, res, turn, async function* () {
        throw new HttpError(429, 'token_quota_exceeded', 'used up');
      }, {});
    } catch (err) { next(err); }
  });
  app.post('/breaks', (req, res) => relay(req, res, turn, async function* () {
    yield { event: 'delta', data: { text: 'half' } };
    throw new Error('upstream died');
  }, {}));
  app.post('/slow', (req, res) => relay(req, res, turn, async function* (signal) {
    yield { event: 'meta', data: {} };
    await new Promise((resolve) => signal.addEventListener('abort', resolve));
    lastUpstreamAborted = true;
  }, {}));
  app.use(errorHandler);
  server = app.listen(0);
  await new Promise((r) => server.once('listening', r));
  base = `http://127.0.0.1:${server.address().port}`;
});
after(() => new Promise((r) => server.close(r)));

async function events(path) {
  const res = await fetch(`${base}${path}`, { method: 'POST' });
  return { res, events: res.body ? await collect(parseSse(res.body)) : [] };
}

test('relay: conversation id first, events in order, done shaped for the app', async () => {
  const { res, events: got } = await events('/ok');
  assert.equal(res.headers.get('content-type'), 'text/event-stream; charset=utf-8');
  assert.deepEqual(got.map((e) => e.event), ['conversation', 'meta', 'delta', 'delta', 'done']);
  assert.equal(got[0].data.conversation_id, turn.conversation.id);
  const done = got.at(-1).data;
  assert.equal(done.answer, 'पानी दें।');
  assert.equal(done.conversation_id, turn.conversation.id);
  assert.ok('usage' in done && !('agent_results' in done), 'internals are not sent to the app');
});

test('relay: an error before the first event is a normal JSON error', async () => {
  const res = await fetch(`${base}/refused`, { method: 'POST' });
  assert.equal(res.status, 429);
  assert.equal((await res.json()).error.code, 'token_quota_exceeded');
});

test('relay: a failure mid-answer ends with an error event, not a hung connection', async () => {
  const { events: got } = await events('/breaks');
  assert.deepEqual(got.map((e) => e.event), ['conversation', 'delta', 'error']);
  assert.equal(got.at(-1).data.code, 'stream_failed');
});

test('relay: the farmer closing the app aborts the upstream call', async () => {
  const controller = new AbortController();
  const res = await fetch(`${base}/slow`, { method: 'POST', signal: controller.signal });
  const reader = res.body.getReader();
  await reader.read();                       // the first events arrived
  controller.abort();
  for (let i = 0; i < 50 && !lastUpstreamAborted; i += 1) await new Promise((r) => setTimeout(r, 10));
  assert.equal(lastUpstreamAborted, true);
});

// ── voice route: refused before any database or AI work ─────────────────────

test('voice: a signed-out caller is refused before any upload is read', async () => {
  const app = createApp().listen(0);
  await new Promise((r) => app.once('listening', r));
  const url = `http://127.0.0.1:${app.address().port}/api/v1/voice/ask`;
  try {
    const res = await fetch(url, {
      method: 'POST', headers: { 'content-type': 'audio/webm' }, body: new Uint8Array(3 * 1024 * 1024),
    });
    assert.equal(res.status, 401);
  } finally {
    await new Promise((r) => app.close(r));
  }
});

test.skip('voice: parameter checks (need a signed-in user and a database)', async () => {
  const app = createApp().listen(0);
  await new Promise((r) => app.once('listening', r));
  const url = `http://127.0.0.1:${app.address().port}/api/v1/voice/ask`;
  try {
    const empty = await fetch(url, { method: 'POST', headers: { 'content-type': 'audio/webm' } });
    assert.equal(empty.status, 400);
    const badId = await fetch(`${url}?farm_id=nope`, {
      method: 'POST', headers: { 'content-type': 'audio/webm' }, body: new Uint8Array([0x1a, 0x45, 0xdf, 0xa3]),
    });
    assert.equal(badId.status, 422);
    const tooLong = await fetch(`${url}?audio_seconds=500`, {
      method: 'POST', headers: { 'content-type': 'audio/webm' }, body: new Uint8Array([0x1a, 0x45, 0xdf, 0xa3]),
    });
    assert.equal(tooLong.status, 413);
    const huge = await fetch(url, {
      method: 'POST', headers: { 'content-type': 'audio/webm' }, body: new Uint8Array(3 * 1024 * 1024),
    });
    assert.equal(huge.status, 413);
  } finally {
    await new Promise((r) => app.close(r));
  }
});
