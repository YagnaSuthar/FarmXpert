/**
 * Record one answered turn: both messages, the run, every agent's output and
 * the plans a farmer acts on.
 *
 *  - Runs AFTER the answer is sent. A database fault costs history, never the
 *    farmer's answer.
 *  - Idempotent: the request id is claimed first; a retried request stores
 *    nothing twice.
 *  - One transaction: half a turn in the history looks complete and is not.
 */

import { transaction } from '../../db/pool.js';
import { logger } from '../../lib/logger.js';
import { pointWkt } from '../../lib/units.js';
import { normaliseUsage, primaryModel, recordUsage } from '../usage.js';
import {
  REQUEST_STATUSES, WEATHER_REUSE_WINDOW_MS, canonicalPayload, cellKey, contentHash, cropRow,
  irrigationRows, isObject, taskPlan, toNumber, unitInterval,
} from './canonical.js';

const FAILED = new Set(['failed', 'timeout', 'invalid_output']);

/**
 * @param turn {{ requestId, conversationId, userId, farmId, fieldId, location, question,
 *                askedAt, language, intents, understanding, inputMode, audioSeconds,
 *                response, latencyMs }}
 * @returns number of rows written, 0 for a duplicate.
 */
export async function recordTurn(turn) {
  const { requestId, response } = turn;
  const answeredAt = new Date();

  return transaction(async (db) => {
    const claimed = await db.query(
      `INSERT INTO idempotency_keys (request_id, recorded_at) VALUES ($1, $2)
       ON CONFLICT (request_id) DO NOTHING RETURNING request_id`,
      [requestId, answeredAt],
    );
    if (!claimed.rowCount) {
      logger.info({ requestId }, 'Turn already recorded');
      return 0;
    }
    let written = 1;

    // Usage first: it is what the quota reads, and the claim above makes it
    // count exactly once however often the request is retried.
    const usage = normaliseUsage(response.usage);
    written += await recordUsage(db, turn.userId ?? null, usage);

    const answer = response.answer || response.summary || '';
    const chat = usage.by_model.filter((m) => m.purpose === 'chat');
    // How the question was read is kept on the farmer's message: it is what
    // answers "which languages fail" and what support staff need to see.
    const understood = turn.understanding || {};
    const inputMode = turn.inputMode === 'voice' ? 'voice' : 'text';
    await db.query(
      `INSERT INTO messages (conversation_id, created_at, role, content, language, request_id,
                             latency_ms, intent, model, prompt_tokens, completion_tokens,
                             script, query_en, input_mode, audio_seconds)
       VALUES ($1, $2, 'farmer', $3, $4, $5, NULL, NULL, NULL, NULL, NULL, $13, $14, $15, $16),
              ($1, $6, 'assistant', $7, $4, $5, $8, $9, $10, $11, $12, NULL, NULL, $15, NULL)`,
      [turn.conversationId, turn.askedAt, turn.question.slice(0, 20000), turn.language, requestId,
        answeredAt, answer.slice(0, 20000), Math.max(0, turn.latencyMs), turn.intents?.[0] ?? null,
        primaryModel(usage)?.slice(0, 80) ?? null,
        chat.length ? chat.reduce((s, m) => s + m.prompt_tokens, 0) : null,
        chat.length ? chat.reduce((s, m) => s + m.completion_tokens, 0) : null,
        typeof understood.script === 'string' ? understood.script.slice(0, 8) : null,
        typeof understood.query_en === 'string' ? understood.query_en.slice(0, 4000) : null,
        inputMode,
        inputMode === 'voice' ? (turn.audioSeconds ?? usage.audio_seconds ?? null) : null],
    );
    if (inputMode === 'voice' && turn.question) {
      // Voice conversations open before the words are known; name them now.
      await db.query(
        `UPDATE conversations SET title = $2 WHERE id = $1 AND title = 'Voice question'`,
        [turn.conversationId, turn.question.slice(0, 160)],
      );
    }
    written += 2;

    const results = Array.isArray(response.agent_results) ? response.agent_results : [];
    const execution = isObject(response.execution) ? response.execution : {};
    await db.query(
      `INSERT INTO orchestration_requests (created_at, request_id, conversation_id, farm_id, field_id,
          intents, status, summary, confidence, duration_ms, agents_succeeded, agents_failed,
          agents_skipped, conflicts, execution, usage, total_tokens)
       VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17)`,
      [answeredAt, requestId, turn.conversationId, turn.farmId, turn.fieldId,
        turn.intents?.length ? JSON.stringify(turn.intents) : null,
        REQUEST_STATUSES.has(response.status) ? response.status : 'failed',
        response.summary ?? null, unitInterval(response.confidence),
        Math.max(0, toNumber(execution.duration_ms) ?? turn.latencyMs),
        results.filter((r) => r.status === 'success').length,
        results.filter((r) => FAILED.has(r.status)).length,
        Array.isArray(response.skipped) ? response.skipped.length : 0,
        response.conflicts?.length ? JSON.stringify(response.conflicts) : null,
        Object.keys(execution).length ? JSON.stringify(execution) : null,
        usage.calls ? JSON.stringify(usage) : null, usage.total_tokens],
    );
    written += 1;

    const outputs = isObject(response.results) ? response.results : {};
    const weather = await weatherSnapshot(db, turn.location, outputs.weather_watcher, answeredAt);
    if (weather?.isNew) written += 1;

    if (results.length) {
      written += await insertAgentOutputs(db, results, outputs, weather, requestId, turn.farmId, answeredAt);
    }
    if (turn.farmId) {
      written += await insertPlans(db, turn, outputs, requestId, answeredAt);
    }
    return written;
  });
}

/** Reference an identical recent forecast for this cell, or store it once. */
async function weatherSnapshot(db, location, forecast, moment) {
  const key = cellKey(location);
  if (!key || !isObject(forecast)) return null;
  const digest = contentHash(forecast);

  // The time bound prunes the lookup to the current partition.
  const found = await db.query(
    `UPDATE weather_snapshots SET reuse_count = reuse_count + 1
      WHERE (id, created_at) = (
        SELECT id, created_at FROM weather_snapshots
         WHERE cell_key = $1 AND content_hash = $2 AND created_at >= $3
         ORDER BY created_at DESC LIMIT 1)
      RETURNING id, created_at`,
    [key, digest, new Date(moment.getTime() - WEATHER_REUSE_WINDOW_MS)],
  );
  if (found.rowCount) return { id: found.rows[0].id, at: found.rows[0].created_at, isNew: false };

  const sources = Array.isArray(forecast.sources) ? forecast.sources.join(',').slice(0, 40) : null;
  const { rows } = await db.query(
    `INSERT INTO weather_snapshots (created_at, cell_key, cell, content_hash, provider, status, forecast)
     VALUES ($1, $2, $3::geography, $4, $5, $6, $7) RETURNING id, created_at`,
    [moment, key, pointWkt(location.lat, location.lon), digest, sources || null,
      forecast.status ? String(forecast.status).slice(0, 16) : null, JSON.stringify(forecast)],
  );
  return { id: rows[0].id, at: rows[0].created_at, isNew: true };
}

/** All agents in one statement: one round trip, not one per agent. */
async function insertAgentOutputs(db, results, outputs, weather, requestId, farmId, moment) {
  const params = [];
  const tuples = results.map((r) => {
    const name = String(r.name).slice(0, 60);
    let payload = null;
    let snapshotId = null;
    let snapshotAt = null;
    if (name === 'weather_watcher' && weather) {
      snapshotId = weather.id;
      snapshotAt = weather.at;
    } else if (outputs[name] !== undefined && outputs[name] !== null) {
      payload = JSON.stringify(canonicalPayload(name, outputs[name]));
    }
    const values = [
      moment, requestId, farmId, name, r.version ? String(r.version).slice(0, 20) : null,
      String(r.status).slice(0, 32), r.error_code ? String(r.error_code).slice(0, 40) : null,
      Math.min(20, Math.max(1, Math.trunc(toNumber(r.attempts) ?? 1))),
      Math.max(0, toNumber(r.duration_ms) ?? 0), unitInterval(r.confidence),
      toNumber(r.data_age_seconds), payload, payload ? Buffer.byteLength(payload) : null,
      snapshotId, snapshotAt,
    ];
    const start = params.length;
    params.push(...values);
    return `(${values.map((_, i) => `$${start + i + 1}`).join(', ')})`;
  });
  await db.query(
    `INSERT INTO agent_outputs (created_at, request_id, farm_id, agent, agent_version, status,
        error_code, attempts, duration_ms, confidence, data_age_s, payload, payload_bytes,
        weather_snapshot_id, weather_snapshot_at)
     VALUES ${tuples.join(', ')}`,
    params,
  );
  return results.length;
}

async function insertPlans(db, turn, outputs, requestId, moment) {
  let written = 0;
  const { farmId, fieldId } = turn;
  const today = moment.toISOString().slice(0, 10);

  const irrigation = irrigationRows(outputs.irrigation_planner);
  if (irrigation.length) {
    // A new plan for a day supersedes the one it replaces, unless the farmer
    // already acted on it.
    await db.query(
      `UPDATE irrigation_plans SET status = 'superseded'
        WHERE farm_id = $1 AND field_id IS NOT DISTINCT FROM $2 AND status = 'planned'
          AND plan_date = ANY($3::date[])`,
      [farmId, fieldId, irrigation.map((r) => r.plan_date)],
    );
    for (const r of irrigation) {
      await db.query(
        `INSERT INTO irrigation_plans (farm_id, field_id, request_id, plan_date, crop, growth_stage,
            decision, water_depth_mm, duration_hours, method, plan, agent_version)
         VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)`,
        [farmId, fieldId, requestId, r.plan_date, r.crop, r.growth_stage, r.decision,
          r.water_depth_mm, r.duration_hours, r.method, JSON.stringify(r.plan), r.agent_version],
      );
    }
    written += irrigation.length;
  }

  const crop = cropRow(outputs.crop_predictor);
  if (crop) {
    await db.query(
      `INSERT INTO crop_recommendations (farm_id, field_id, request_id, input_data, recommendations,
          top_crop, confidence, agent_version, season)
       VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)`,
      [farmId, fieldId, requestId, JSON.stringify(crop.input_data), JSON.stringify(crop.recommendations),
        crop.top_crop, crop.confidence, crop.agent_version, crop.season],
    );
    written += 1;
  }

  const plan = taskPlan(outputs.task_scheduler);
  if (plan) {
    // Open tasks from an older plan are replaced by the new one's.
    await db.query(
      `UPDATE scheduled_tasks SET status = 'cancelled'
        WHERE farm_id = $1 AND field_id IS NOT DISTINCT FROM $2 AND status = 'scheduled'`,
      [farmId, fieldId],
    );
    const { rows } = await db.query(
      `INSERT INTO task_plans (farm_id, field_id, request_id, plan_date, horizon_days, headline,
          summary, plan, agent_version)
       VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9) RETURNING id`,
      [farmId, fieldId, requestId, plan.plan_date || today, plan.horizon_days, plan.headline,
        plan.summary, JSON.stringify(plan.plan), plan.agent_version],
    );
    if (plan.tasks.length) {
      const t = plan.tasks;
      await db.query(
        `INSERT INTO scheduled_tasks (task_plan_id, farm_id, field_id, title, category, priority,
            status, scheduled_date, scheduled_start_time, duration_minutes, why_now, detail)
         SELECT $1, $2, $3, * FROM unnest($4::text[], $5::text[], $6::text[], $7::text[],
                                         $8::date[], $9::text[], $10::int[], $11::text[], $12::jsonb[])`,
        [rows[0].id, farmId, fieldId, t.map((x) => x.title), t.map((x) => x.category),
          t.map((x) => x.priority), t.map((x) => x.status), t.map((x) => x.scheduled_date),
          t.map((x) => x.scheduled_start_time), t.map((x) => x.duration_minutes),
          t.map((x) => x.why_now), t.map((x) => (x.detail ? JSON.stringify(x.detail) : null))],
      );
    }
    written += 1 + plan.tasks.length;
  }
  return written;
}
