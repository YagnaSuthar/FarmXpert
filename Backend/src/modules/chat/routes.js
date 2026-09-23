/**
 * The farmer's conversation with FarmXpert.
 *
 * POST /chat/ask (typed; JSON or streamed) and POST /voice/ask (spoken), in order:
 *   1. Check the allowance, then resolve everything the AI needs in parallel -
 *      the farm's location, the field's crop, the newest soil reading, the last
 *      turns - a few indexed lookups, ~2 ms. The AI backend is stateless and
 *      never queries for them itself.
 *   2. Ask the AI backend (blocking, or streamed as server-sent events).
 *   3. Answer the farmer - streamed answers reach the app as they are written.
 *   4. Then record the turn (recordTurn), off the response path.
 */

import { randomUUID } from 'node:crypto';

import express, { Router } from 'express';

import { ai } from '../../clients/ai.js';
import { config } from '../../config/env.js';
import { one, query } from '../../db/pool.js';
import { HttpError, badRequest, notFound } from '../../lib/errors.js';
import { logger } from '../../lib/logger.js';
import { rateLimit } from '../../lib/rateLimit.js';
import { decodeCursor, toPage } from '../../lib/paging.js';
import { idParam, pageQuery, uuid, validate } from '../../lib/validate.js';
import { STAFF, authenticate } from '../auth/middleware.js';
import { READING_FIELDS, latestReading } from '../soil.js';
import { expandPayload } from './canonical.js';
import { assertWithinQuota, normaliseUsage } from '../usage.js';
import { recordTurn } from './persist.js';

export const chatRoutes = Router();

const HISTORY_TURNS = 6;
// Mirrors AI_Backend/orchestration/planner.py Intent.
const INTENTS = ['daily_plan', 'irrigation', 'crop_choice', 'soil', 'weather', 'market', 'ask', 'full_scan'];

// Recording runs after the response; shutdown waits for these to finish.
const pending = new Set();
export async function drainPendingTurns(timeoutMs = 10000) {
  if (!pending.size) return;
  await Promise.race([Promise.allSettled([...pending]), new Promise((r) => setTimeout(r, timeoutMs))]);
}

const askProperties = {
  farm_id: uuid,
  field_id: uuid,
  conversation_id: uuid,
  request_id: { type: 'string', pattern: '^[A-Za-z0-9_.:-]{8,64}$' },
  // A hint only: the language is detected from the words themselves. When
  // absent the farmer's profile language is used.
  language: { type: 'string', maxLength: 12 },
  channel: { enum: ['app', 'whatsapp', 'voice', 'sms', 'web', 'mcp', 'api'], default: 'app' },
};

const askBody = {
  type: 'object',
  properties: {
    ...askProperties,
    query: { type: 'string', minLength: 1, maxLength: 2000 },
    intents: { type: 'array', items: { type: 'string', maxLength: 32 }, maxItems: 8 },
    explain: { type: 'boolean', default: true },
    stream: { type: 'boolean', default: false },
    // What the farmer states in this turn overrides what is stored.
    crop: { type: 'object', additionalProperties: true },
    market: { type: 'object', additionalProperties: true },
  },
  required: ['query'],
};

/**
 * Typed question. JSON by default; server-sent events when the client sends
 * `Accept: text/event-stream` or `"stream": true`:
 *   meta, delta..., done   (see AI_Backend /orchestrator/execute/stream)
 */
const chatLimit = rateLimit({ perMinute: config.rateLimit.chatPerMinute, name: 'chat' });
const voiceLimit = rateLimit({ perMinute: config.rateLimit.voicePerMinute, name: 'voice' });

chatRoutes.post('/chat/ask', authenticate, validate({ body: askBody }), chatLimit, async (req, res) => {
  const turn = await prepareTurn({ ...req.body, user_id: req.user.id }, { inputMode: 'text' });
  const wantsStream = req.body.stream || (req.get('accept') || '').includes('text/event-stream');

  if (!wantsStream) {
    const { status, data } = await ai.execute(turn.aiRequest, turn.requestId);
    if (status === 422 || !data) {
      throw new HttpError(422, 'validation_failed', data?.message || 'The question could not be processed.',
        data?.problems);
    }
    res.json(clientView(turn, data));
    finishTurn(turn, data, { question: req.body.query });
    return;
  }

  await relay(req, res, turn, (signal) => ai.executeStream(turn.aiRequest, turn.requestId, signal),
    { question: req.body.query });
});

/**
 * Spoken question: the raw recording is the body (audio/webm, audio/ogg,
 * audio/mp4, audio/mpeg, audio/wav; at most VOICE_MAX_BYTES), the ids are the
 * query string. Always server-sent events:
 *   transcript, meta, delta..., audio... (one clip per sentence), done
 * The audio is forwarded and never stored; the transcript is.
 */
chatRoutes.post(
  '/voice/ask',
  authenticate,
  voiceLimit,
  express.raw({ type: ['audio/*', 'application/octet-stream'], limit: config.voice.maxBytes }),
  validate({
    query: {
      type: 'object',
      properties: { ...askProperties, audio_seconds: { type: 'number', exclusiveMinimum: 0, maximum: 600 } },
    },
  }),
  async (req, res) => {
    if (!Buffer.isBuffer(req.body) || !req.body.length) {
      throw badRequest('Send the recording as the request body with an audio/* content type.');
    }
    const q = req.query;
    if (q.audio_seconds && q.audio_seconds > config.voice.maxSeconds) {
      throw new HttpError(413, 'audio_too_long', 'The recording is too long. Please keep it under a minute.');
    }
    const turn = await prepareTurn({ ...q, user_id: req.user.id, query: null, channel: q.channel || 'voice' },
      { inputMode: 'voice' });

    const form = new FormData();
    form.append('audio', new Blob([req.body], { type: req.get('content-type') }), 'question');
    // The AI fills the question in from the transcript.
    const { query: _unused, ...voiceRequest } = turn.aiRequest;
    form.append('request', JSON.stringify(voiceRequest));
    if (q.audio_seconds) form.append('audio_seconds', String(q.audio_seconds));

    await relay(req, res, turn, (signal) => ai.voiceStream(form, turn.requestId, signal),
      { audioSeconds: q.audio_seconds ?? null });
  },
);

/** Everything before the AI is asked: quota, context, conversation, history. */
async function prepareTurn(b, { inputMode }) {
  const askedAt = new Date();
  const started = performance.now();
  const requestId = b.request_id || randomUUID();
  const unknown = (b.intents || []).filter((i) => !INTENTS.includes(i));
  if (unknown.length) throw badRequest(`Unknown intent: ${unknown.join(', ')}`);

  // The allowance is checked before anything is created or any token spent.
  const quota = b.user_id ? await assertWithinQuota(b.user_id, { voice: inputMode === 'voice' }) : null;
  const language = b.language || quota?.language || 'en';

  const [conversation, farm, field, soil] = await Promise.all([
    resolveConversation({ ...b, language, query: b.query ?? 'Voice question' }),
    b.farm_id ? one(
      `SELECT id, user_id, latitude, longitude, state, district, area_hectares::float8 AS area_hectares,
              resources, water_source
         FROM farms WHERE id = $1 AND deleted_at IS NULL`, [b.farm_id]) : null,
    b.field_id ? one(
      `SELECT id, farm_id, crop_name, growth_stage, sown_on, expected_harvest_on, soil_type,
              irrigation_method, area_hectares::float8 AS area_hectares
         FROM fields WHERE id = $1 AND deleted_at IS NULL`, [b.field_id]) : null,
    b.farm_id ? latestReading(b.farm_id, b.field_id ?? null) : null,
  ]);
  if (b.farm_id && !farm) throw notFound('Farm');
  if (b.field_id && (!field || field.farm_id !== b.farm_id)) throw notFound('Field on this farm');
  if (farm && farm.user_id !== b.user_id) throw notFound('Farm');

  const history = conversation.existing ? await recentTurns(conversation) : [];
  const aiRequest = buildAiRequest({ body: { ...b, language }, requestId, farm, field, soil, history });
  return { requestId, askedAt, started, conversation, farm, field, aiRequest, language, inputMode, body: b };
}

/** The response the app sees: the AI's answer minus internals. */
function clientView(turn, data) {
  return {
    conversation_id: turn.conversation.id,
    request_id: data.request_id || turn.requestId,
    status: data.status,
    answer: data.answer ?? null,
    summary: data.summary,
    understanding: data.understanding ?? null,
    confidence: data.confidence ?? null,
    results: data.results ?? {},
    conflicts: data.conflicts ?? [],
    warnings: data.warnings ?? [],
    skipped: data.skipped ?? [],
    provenance: data.provenance ?? [],
    usage: normaliseUsage(data.usage),
    ...(data.transcript ? { transcript: data.transcript } : {}),
  };
}

/** Record the turn after the farmer has the answer. Never throws. */
function finishTurn(turn, data, { question, audioSeconds = null }) {
  const job = recordTurn({
    requestId: data.request_id || turn.requestId,
    conversationId: turn.conversation.id,
    userId: turn.body.user_id ?? null,
    farmId: turn.farm?.id ?? null,
    fieldId: turn.field?.id ?? null,
    location: turn.aiRequest.location ?? null,
    question: question ?? data.transcript ?? '',
    askedAt: turn.askedAt,
    language: data.understanding?.language || turn.language,
    intents: turn.body.intents?.length ? turn.body.intents
      : (data.understanding?.intent ? [data.understanding.intent] : []),
    understanding: data.understanding ?? null,
    inputMode: turn.inputMode,
    audioSeconds,
    response: data,
    latencyMs: performance.now() - turn.started,
  })
    .catch((err) => logger.error({ err, requestId: turn.requestId }, 'Recording the turn failed; the farmer was answered'))
    .finally(() => pending.delete(job));
  pending.add(job);
}

/**
 * Pass the AI's event stream to the app as it arrives, then record the turn
 * from the final `done` event. The farmer closing the app aborts the AI call.
 */
export async function relay(req, res, turn, open, finishOptions) {
  const upstream = new AbortController();
  res.on('close', () => { if (!res.writableEnded) upstream.abort(); });

  // Errors before the first byte still get the normal JSON error response.
  const events = open(upstream.signal);
  let first;
  try {
    first = await events.next();
  } catch (err) {
    if (err?.name === 'AbortError') return;
    throw err;
  }

  res.status(200).set({
    'Content-Type': 'text/event-stream; charset=utf-8',
    'Cache-Control': 'no-cache, no-transform',
    Connection: 'keep-alive',
    'X-Accel-Buffering': 'no',
  });
  res.flushHeaders();
  // Keeps proxies and mobile networks from closing a quiet connection while
  // the agents work.
  const heartbeat = setInterval(() => res.write(': keep-alive\n\n'), 15000);
  const send = (event, data) => res.write(`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`);
  send('conversation', { conversation_id: turn.conversation.id, request_id: turn.requestId });

  try {
    for (let item = first; !item.done; item = await events.next()) {
      const { event, data } = item.value;
      if (event === 'done') {
        send('done', clientView(turn, data));
        finishTurn(turn, data, finishOptions);
      } else {
        send(event, data);
      }
    }
  } catch (err) {
    if (err?.name !== 'AbortError') {
      logger.error({ err, requestId: turn.requestId }, 'Stream relay failed');
      send('error', { code: 'stream_failed', message: 'The answer was interrupted. Please ask again.' });
    }
  } finally {
    clearInterval(heartbeat);
    if (!res.writableEnded) res.end();
  }
}

/** Use the given conversation or open one. `existing` says whether it has history. */
async function resolveConversation(b) {
  if (b.conversation_id) {
    const found = await one(
      `SELECT id, user_id, started_at, message_count FROM conversations WHERE id = $1`,
      [b.conversation_id],
    );
    if (!found || found.user_id !== b.user_id) {
      throw notFound('Conversation');
    }
    return { ...found, existing: found.message_count > 0 };
  }
  const created = await one(
    `INSERT INTO conversations (user_id, farm_id, field_id, channel, language, title)
     VALUES ($1, $2, $3, $4, $5, $6) RETURNING id, started_at`,
    [b.user_id ?? null, b.farm_id ?? null, b.field_id ?? null, b.channel, b.language,
      b.query.slice(0, 160)],
  );
  return { ...created, existing: false };
}

/** Last turns, oldest first. Bounded by started_at so old partitions are skipped. */
async function recentTurns(conversation) {
  const { rows } = await query(
    `SELECT role, content FROM messages
      WHERE conversation_id = $1 AND created_at >= $2 AND role IN ('farmer', 'assistant')
      ORDER BY created_at DESC, id DESC LIMIT $3`,
    [conversation.id, conversation.started_at, HISTORY_TURNS * 2],
  );
  return rows.reverse().map((r) => ({ role: r.role, content: r.content.slice(0, 4000) }));
}

export function buildAiRequest({ body, requestId, farm, field, soil, history }) {
  const request = {
    request_id: requestId,
    query: body.query,
    language: body.language || 'en',
    explain: body.explain ?? true,
    history,
  };
  if (farm) request.farm_id = farm.id;
  if (body.intents?.length) request.intents = body.intents;
  if (farm && farm.latitude !== null && farm.longitude !== null) {
    request.location = { lat: farm.latitude, lon: farm.longitude };
  }

  const soilOut = {};
  if (soil) {
    for (const key of READING_FIELDS) if (soil[key] !== null && soil[key] !== undefined) soilOut[key] = soil[key];
    soilOut.recorded_at = soil.recorded_at instanceof Date ? soil.recorded_at.toISOString() : soil.recorded_at;
  }
  if (!soilOut.soil_type && field?.soil_type) soilOut.soil_type = field.soil_type;
  if (Object.keys(soilOut).length) request.soil = soilOut;

  const crop = {};
  if (field) {
    if (field.crop_name) crop.name = field.crop_name;
    if (field.growth_stage) crop.growth_stage = field.growth_stage;
    if (field.irrigation_method) crop.irrigation_method = field.irrigation_method;
    if (field.sown_on) crop.days_after_sowing = daysSince(field.sown_on);
    if (field.expected_harvest_on) crop.days_to_harvest = Math.max(0, -daysSince(field.expected_harvest_on));
    crop.area_hectares = field.area_hectares ?? farm?.area_hectares ?? undefined;
    crop.field_id = field.id;
  } else if (farm?.area_hectares) {
    crop.area_hectares = farm.area_hectares;
  }
  Object.assign(crop, body.crop || {});
  for (const k of Object.keys(crop)) if (crop[k] === undefined || crop[k] === null) delete crop[k];
  if (Object.keys(crop).length) request.crop = crop;

  // What the task scheduler plans within; rainfed land cannot be irrigated.
  const resources = { ...(farm?.resources || {}) };
  if (resources.irrigation_available === undefined && (field?.irrigation_method || farm?.water_source)) {
    resources.irrigation_available = field?.irrigation_method !== 'rainfed' && farm?.water_source !== 'rainfed';
  }
  if (Object.keys(resources).length) request.resources = resources;

  const market = { ...(farm?.state ? { state: farm.state } : {}), ...(farm?.district ? { district: farm.district } : {}), ...(body.market || {}) };
  if (Object.keys(market).length) request.market = market;
  return request;
}

function daysSince(dateValue) {
  const d = dateValue instanceof Date ? dateValue : new Date(`${String(dateValue).slice(0, 10)}T00:00:00Z`);
  return Math.floor((Date.now() - d.getTime()) / 86_400_000);
}

// ── history ─────────────────────────────────────────────────────────────────

chatRoutes.get(
  '/conversations',
  authenticate,
  validate({ query: { type: 'object', properties: { user_id: uuid, ...pageQuery } } }),
  async (req, res) => {
    const { limit, cursor } = req.query;
    const userId = STAFF.has(req.user.role) && req.query.user_id ? req.query.user_id : req.user.id;
    const after = decodeCursor(cursor);
    const { rows } = await query(
      `SELECT id, farm_id, field_id, channel, language, title, status, message_count,
              started_at, last_message_at
         FROM conversations
        WHERE user_id = $1 AND ($2::timestamptz IS NULL OR (last_message_at, id) < ($2, $3::uuid))
        ORDER BY last_message_at DESC, id DESC LIMIT $4`,
      [userId, after?.at ?? null, after?.id ?? null, limit + 1],
    );
    res.json(toPage(rows, limit, (r) => [r.last_message_at, r.id]));
  },
);

chatRoutes.get(
  '/conversations/:id/messages',
  authenticate,
  validate({ params: idParam, query: { type: 'object', properties: pageQuery } }),
  async (req, res) => {
    const conversation = await one('SELECT id, user_id, started_at FROM conversations WHERE id = $1', [req.params.id]);
    if (!conversation || (conversation.user_id !== req.user.id && !STAFF.has(req.user.role))) {
      throw notFound('Conversation');
    }
    const { limit, cursor } = req.query;
    const after = decodeCursor(cursor);
    const { rows } = await query(
      `SELECT id, created_at, role, content, language, request_id, intent, latency_ms::float8 AS latency_ms, feedback
         FROM messages
        WHERE conversation_id = $1 AND created_at >= $2
          AND ($3::timestamptz IS NULL OR (created_at, id) < ($3, $4::uuid))
        ORDER BY created_at DESC, id DESC LIMIT $5`,
      [conversation.id, conversation.started_at, after?.at ?? null, after?.id ?? null, limit + 1],
    );
    res.json(toPage(rows, limit, (r) => [r.created_at, r.id]));
  },
);

chatRoutes.post(
  '/chat/feedback',
  authenticate,
  validate({
    body: {
      type: 'object',
      properties: {
        request_id: { type: 'string', minLength: 1, maxLength: 64 },
        value: { enum: [-1, 0, 1] },
      },
      required: ['request_id', 'value'],
    },
  }),
  async (req, res) => {
    // Served by the partial request_id index on each monthly partition.
    const { rowCount } = await query(
      `UPDATE messages m SET feedback = $2
        WHERE m.request_id = $1 AND m.role = 'assistant'
          AND EXISTS (SELECT 1 FROM conversations c WHERE c.id = m.conversation_id AND c.user_id = $3)`,
      [req.body.request_id, req.body.value, req.user.id],
    );
    if (!rowCount) throw notFound('Answer');
    res.status(204).end();
  },
);

// Everything recorded for one request: what each agent said, and why.
chatRoutes.get(
  '/requests/:requestId',
  authenticate,
  validate({ params: { type: 'object', properties: { requestId: { type: 'string', maxLength: 64 } }, required: ['requestId'] } }),
  async (req, res) => {
    const run = await one(
      `SELECT r.request_id, r.created_at, r.conversation_id, r.farm_id, r.field_id, r.intents, r.status,
              r.summary, r.confidence, r.duration_ms::float8 AS duration_ms, r.agents_succeeded,
              r.agents_failed, r.agents_skipped, r.conflicts, r.execution
         FROM orchestration_requests r
         LEFT JOIN conversations c ON c.id = r.conversation_id
        WHERE r.request_id = $1 AND (c.user_id = $2 OR $3)
        ORDER BY r.created_at DESC LIMIT 1`,
      [req.params.requestId, req.user.id, STAFF.has(req.user.role)],
    );
    if (!run) throw notFound('Request');
    const { rows } = await query(
      `SELECT a.agent, a.agent_version, a.status, a.error_code, a.attempts,
              a.duration_ms::float8 AS duration_ms, a.confidence, a.data_age_s,
              COALESCE(a.payload, w.forecast) AS payload
         FROM agent_outputs a
         LEFT JOIN weather_snapshots w
           ON w.id = a.weather_snapshot_id AND w.created_at = a.weather_snapshot_at
        WHERE a.request_id = $1 AND a.created_at = $2
        ORDER BY a.agent`,
      [run.request_id, run.created_at],
    );
    res.json({ ...run, agents: rows.map((r) => ({ ...r, payload: expandPayload(r.agent, r.payload) })) });
  },
);
