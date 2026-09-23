/**
 * Token usage: recording, quotas, cost and reports.
 *
 *  - Counts come from the AI backend's `usage` block: the provider's own
 *    numbers, per model, for every call made while answering one question.
 *  - Quota: before a question reaches the AI, the farmer's usage for their
 *    local day is one primary-key lookup. The limit is soft by design: two
 *    questions racing past it may overshoot by one answer, which is cheaper
 *    than serialising every farmer's questions behind a lock.
 *  - Recording happens inside the idempotent turn transaction, so a retried
 *    request is never counted twice.
 */

import { Router } from 'express';

import { config } from '../config/env.js';
import { one, query } from '../db/pool.js';
import { HttpError, notFound } from '../lib/errors.js';
import { idParam, validate } from '../lib/validate.js';
import { requireAdmin } from './admin.js';
import { STAFF, authenticate } from './auth/middleware.js';

export const usageRoutes = Router();

const ANONYMOUS = '00000000-0000-0000-0000-000000000000';
// The farmer's calendar day, in SQL, for a parameter holding the time zone.
const LOCAL_DAY = (tzParam) => `(now() AT TIME ZONE ${tzParam})::date`;

// ── pure helpers (unit tested) ──────────────────────────────────────────────

const count = (v) => (Number.isFinite(Number(v)) && Number(v) >= 0 ? Math.trunc(Number(v)) : 0);
const seconds = (v) => (Number.isFinite(Number(v)) && Number(v) >= 0
  ? Math.min(86400, Math.round(Number(v) * 100) / 100) : 0);
const PURPOSES = new Set(['chat', 'embedding', 'transcription', 'speech']);

/**
 * The AI's usage block, made safe to store: bounded counts, known purposes,
 * at most 20 models. Anything malformed becomes zero, never an exception -
 * a bad usage block must not cost the farmer's history.
 */
export function normaliseUsage(raw) {
  const models = (Array.isArray(raw?.by_model) ? raw.by_model : [])
    .slice(0, 20)
    .filter((m) => m && typeof m.model === 'string' && m.model)
    .map((m) => ({
      model: m.model.slice(0, 120),
      purpose: PURPOSES.has(m.purpose) ? m.purpose : 'chat',
      calls: count(m.calls),
      prompt_tokens: count(m.prompt_tokens),
      completion_tokens: count(m.completion_tokens),
      estimated: Boolean(m.estimated),
      audio_seconds: seconds(m.audio_seconds),
      characters: count(m.characters),
    }));
  const prompt = models.reduce((s, m) => s + m.prompt_tokens, 0);
  const completion = models.reduce((s, m) => s + m.completion_tokens, 0);
  return {
    prompt_tokens: prompt,
    completion_tokens: completion,
    total_tokens: prompt + completion,
    calls: models.reduce((s, m) => s + m.calls, 0),
    estimated: models.some((m) => m.estimated),
    audio_seconds: Math.round(models.reduce((s, m) => s + m.audio_seconds, 0) * 100) / 100,
    characters: models.reduce((s, m) => s + m.characters, 0),
    by_model: models,
  };
}

/**
 * Cost of one model's usage at the configured price; null if unpriced.
 * Tokens per 1M (input/output), speech-to-text per minute of audio,
 * text-to-speech per 1M characters - whichever the price defines.
 */
export function costOf(model, use, prices = config.tokens.prices) {
  const price = prices[model];
  if (!price) return null;
  const cost = ((use.prompt_tokens || 0) * (price.input || 0)
    + (use.completion_tokens || 0) * (price.output || 0)) / 1e6
    + ((use.audio_seconds || 0) / 60) * (price.per_minute || 0)
    + ((use.characters || 0) * (price.per_1m_characters || 0)) / 1e6;
  return Math.round(cost * 1e6) / 1e6;
}

/** The chat model that wrote most of the answer: the one to show on the message. */
export function primaryModel(usage) {
  const chat = usage.by_model.filter((m) => m.purpose === 'chat');
  if (!chat.length) return null;
  return chat.reduce((a, b) => (b.completion_tokens > a.completion_tokens ? b : a)).model;
}

// ── quota ───────────────────────────────────────────────────────────────────

/** Today's usage against the limit for one farmer. `limit` null = unlimited. */
export async function quotaStatus(userId) {
  const row = await one(
    `SELECT u.token_daily_limit, u.language, t.used, t.voice_seconds,
            ((${LOCAL_DAY('$2')} + 1)::timestamp AT TIME ZONE $2) AS resets_at
       FROM users u
       CROSS JOIN LATERAL (
         SELECT COALESCE(sum(total_tokens), 0)::bigint AS used,
                COALESCE(sum(audio_seconds), 0)::float8 AS voice_seconds
           FROM token_usage_daily d
          WHERE d.user_id = u.id AND d.usage_date = ${LOCAL_DAY('$2')}) t
      WHERE u.id = $1 AND u.deleted_at IS NULL`,
    [userId, config.tokens.timezone],
  );
  if (!row) return null;
  const configured = row.token_daily_limit ?? config.tokens.dailyLimit;
  // A per-user 0 blocks; the deployment default 0 means "no limit".
  const limit = row.token_daily_limit === 0 ? 0 : configured || null;
  return {
    limit,
    used: row.used,
    remaining: limit === null ? null : Math.max(0, limit - row.used),
    voice_seconds_used: row.voice_seconds,
    voice_seconds_limit: config.voice.dailySeconds || null,
    resets_at: row.resets_at,
    timezone: config.tokens.timezone,
    language: row.language,
  };
}

/** Throw 429 when the farmer has used today's allowance (and, for voice, speech minutes). */
export async function assertWithinQuota(userId, { voice = false } = {}) {
  const status = await quotaStatus(userId);
  if (!status) throw notFound('User');
  const { language, ...visible } = status;
  if (status.limit !== null && status.used >= status.limit) {
    throw new HttpError(429, 'token_quota_exceeded',
      'Today\'s question allowance is used up. It resets at midnight.', visible);
  }
  if (voice && status.voice_seconds_limit && status.voice_seconds_used >= status.voice_seconds_limit) {
    throw new HttpError(429, 'voice_quota_exceeded',
      'Today\'s voice allowance is used up. You can still type your question.', visible);
  }
  return status;
}

// ── recording (called inside the turn transaction) ──────────────────────────

/** Add one answer's usage to the farmer's day. Returns rows written. */
export async function recordUsage(db, userId, usage) {
  if (!usage.by_model.length) return 0;
  const m = usage.by_model;
  await db.query(
    `INSERT INTO token_usage_daily (usage_date, user_id, model, purpose, prompt_tokens,
                                    completion_tokens, calls, estimated_calls, cost,
                                    audio_seconds, characters)
     SELECT ${LOCAL_DAY('$1')}, $2::uuid, x.model, x.purpose, x.p, x.c, x.calls, x.est, x.cost,
            x.secs, x.chars
       FROM unnest($3::text[], $4::text[], $5::bigint[], $6::bigint[], $7::int[], $8::int[],
                   $9::numeric[], $10::numeric[], $11::bigint[])
            AS x(model, purpose, p, c, calls, est, cost, secs, chars)
     ON CONFLICT (usage_date, COALESCE(user_id, '${ANONYMOUS}'::uuid), model) DO UPDATE SET
         prompt_tokens     = token_usage_daily.prompt_tokens + EXCLUDED.prompt_tokens,
         completion_tokens = token_usage_daily.completion_tokens + EXCLUDED.completion_tokens,
         calls             = token_usage_daily.calls + EXCLUDED.calls,
         estimated_calls   = token_usage_daily.estimated_calls + EXCLUDED.estimated_calls,
         cost              = token_usage_daily.cost + EXCLUDED.cost,
         audio_seconds     = token_usage_daily.audio_seconds + EXCLUDED.audio_seconds,
         characters        = token_usage_daily.characters + EXCLUDED.characters`,
    [config.tokens.timezone, userId, m.map((x) => x.model), m.map((x) => x.purpose),
      m.map((x) => x.prompt_tokens), m.map((x) => x.completion_tokens), m.map((x) => x.calls),
      m.map((x) => (x.estimated ? x.calls : 0)),
      m.map((x) => costOf(x.model, x) ?? 0),
      m.map((x) => x.audio_seconds), m.map((x) => x.characters)],
  );
  return m.length;
}

// ── reports ─────────────────────────────────────────────────────────────────

const range = {
  type: 'object',
  properties: {
    from: { type: 'string', format: 'date' },
    to: { type: 'string', format: 'date' },
  },
};

function bounds(q) {
  // Default: the last 30 local days, today included.
  return [q.from ?? null, q.to ?? null, config.tokens.timezone];
}

usageRoutes.get('/users/:id/usage', authenticate, validate({ params: idParam, query: range }), async (req, res) => {
  if (req.user.id !== req.params.id && !STAFF.has(req.user.role)) throw notFound('User');
  const quota = await quotaStatus(req.params.id);
  if (!quota) throw notFound('User');
  const { rows } = await query(
    `SELECT usage_date, model, purpose, prompt_tokens, completion_tokens, total_tokens, calls,
            estimated_calls, audio_seconds::float8 AS audio_seconds, characters, cost::float8 AS cost
       FROM token_usage_daily
      WHERE user_id = $1
        AND usage_date >= COALESCE($2::date, ${LOCAL_DAY('$4')} - 29)
        AND usage_date <= COALESCE($3::date, ${LOCAL_DAY('$4')})
      ORDER BY usage_date DESC, model`,
    [req.params.id, ...bounds(req.query)],
  );
  res.json({ today: quota, currency: config.tokens.currency, totals: totals(rows), days: rows });
});

usageRoutes.get('/admin/usage', requireAdmin, validate({ query: range }), async (req, res) => {
  const params = bounds(req.query);
  const window = `usage_date >= COALESCE($1::date, ${LOCAL_DAY('$3')} - 29)
                  AND usage_date <= COALESCE($2::date, ${LOCAL_DAY('$3')})`;
  const [byModel, byDay, topUsers] = await Promise.all([
    query(`SELECT model, purpose, sum(prompt_tokens)::bigint AS prompt_tokens,
                  sum(completion_tokens)::bigint AS completion_tokens, sum(total_tokens)::bigint AS total_tokens,
                  sum(calls)::bigint AS calls, sum(estimated_calls)::bigint AS estimated_calls,
                  sum(audio_seconds)::float8 AS audio_seconds, sum(characters)::bigint AS characters,
                  sum(cost)::float8 AS cost
             FROM token_usage_daily WHERE ${window} GROUP BY model, purpose ORDER BY total_tokens DESC`, params),
    query(`SELECT usage_date, sum(total_tokens)::bigint AS total_tokens, sum(cost)::float8 AS cost,
                  count(DISTINCT user_id)::int AS active_users
             FROM token_usage_daily WHERE ${window} GROUP BY usage_date ORDER BY usage_date DESC`, params),
    query(`SELECT user_id, sum(total_tokens)::bigint AS total_tokens, sum(cost)::float8 AS cost
             FROM token_usage_daily WHERE ${window} AND user_id IS NOT NULL
            GROUP BY user_id ORDER BY total_tokens DESC LIMIT 20`, params),
  ]);
  const priced = new Set(Object.keys(config.tokens.prices));
  res.json({
    currency: config.tokens.currency,
    totals: totals(byModel.rows),
    by_model: byModel.rows.map((r) => ({ ...r, priced: priced.has(r.model) })),
    by_day: byDay.rows,
    top_users: topUsers.rows,
  });
});

usageRoutes.put(
  '/admin/users/:id/token-limit',
  requireAdmin,
  validate({
    params: idParam,
    body: {
      type: 'object',
      properties: { limit: { type: ['integer', 'null'], minimum: 0 } },
      required: ['limit'],
    },
  }),
  async (req, res) => {
    const user = await one(
      'UPDATE users SET token_daily_limit = $2 WHERE id = $1 AND deleted_at IS NULL RETURNING id',
      [req.params.id, req.body.limit],
    );
    if (!user) throw notFound('User');
    res.json(await quotaStatus(req.params.id));
  },
);

function totals(rows) {
  const sum = (k) => rows.reduce((s, r) => s + Number(r[k] || 0), 0);
  return {
    prompt_tokens: sum('prompt_tokens'),
    completion_tokens: sum('completion_tokens'),
    total_tokens: sum('total_tokens'),
    calls: sum('calls'),
    audio_seconds: Math.round(sum('audio_seconds') * 100) / 100,
    characters: sum('characters'),
    cost: Math.round(sum('cost') * 1e6) / 1e6,
  };
}
