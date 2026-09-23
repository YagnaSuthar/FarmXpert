/**
 * The form agent output is stored in. Pure functions, no I/O: unit tested.
 *
 * Each fact is stored once:
 *  - The task scheduler's `daily_plans` and `critical_tasks` are views of
 *    `all_tasks`. They were 39 KB of a measured 74 KB request, so they are
 *    dropped on write and rebuilt on read (`expandPayload`), loss-free.
 *  - Weather goes to weather_snapshots, shared by every farm in the ~1 km
 *    cell, and agent_outputs only references it.
 */

import { createHash } from 'node:crypto';

const DERIVED_TASK_FIELDS = ['daily_plans', 'critical_tasks'];
export const PRIORITIES = new Set(['critical', 'high', 'medium', 'low', 'deferred']);
export const TASK_STATUSES = new Set(['scheduled', 'delayed', 'skipped', 'done', 'cancelled']);
export const REQUEST_STATUSES = new Set(['success', 'partial_success', 'failed', 'validation_error']);

// The Weather Watcher caches a forecast for 15 minutes per cell; an identical
// snapshot inside this window is the same forecast.
export const WEATHER_REUSE_WINDOW_MS = 30 * 60 * 1000;

export function canonicalPayload(agent, payload) {
  if (agent === 'task_scheduler' && isObject(payload)) {
    const out = { ...payload };
    for (const key of DERIVED_TASK_FIELDS) delete out[key];
    return out;
  }
  return payload;
}

/** Rebuild the views `canonicalPayload` dropped. */
export function expandPayload(agent, payload) {
  if (agent !== 'task_scheduler' || !isObject(payload)) return payload;
  const tasks = Array.isArray(payload.all_tasks) ? payload.all_tasks : [];
  const byDay = new Map();
  for (const task of tasks) {
    const day = task?.scheduled_date || task?.delay_until_date;
    if (!day) continue;
    const key = String(day);
    if (!byDay.has(key)) byDay.set(key, []);
    byDay.get(key).push(task);
  }
  const startOf = (t) => t.scheduled_start_time || '99:99';
  return {
    ...payload,
    critical_tasks: tasks.filter((t) => t?.priority === 'critical'),
    daily_plans: [...byDay.keys()].sort().map((day) => {
      const items = [...byDay.get(day)].sort((a, b) => (startOf(a) < startOf(b) ? -1 : startOf(a) > startOf(b) ? 1 : 0));
      return {
        plan_date: day,
        tasks: items,
        total_tasks: items.length,
        critical_tasks: items.filter((t) => t.priority === 'critical').length,
      };
    }),
  };
}

/** JSON with sorted keys at every level: equal values give equal text. */
export function stableStringify(value) {
  if (value === null || typeof value !== 'object') return JSON.stringify(value) ?? 'null';
  if (Array.isArray(value)) return `[${value.map(stableStringify).join(',')}]`;
  const keys = Object.keys(value).filter((k) => value[k] !== undefined).sort();
  return `{${keys.map((k) => `${JSON.stringify(k)}:${stableStringify(value[k])}`).join(',')}}`;
}

export function contentHash(value) {
  return createHash('sha256').update(stableStringify(value)).digest('hex');
}

/** The weather cache's own cell (2 dp, ~1.1 km), so dedup matches what the cache shares. */
export function cellKey(location) {
  if (!location || !Number.isFinite(location.lat) || !Number.isFinite(location.lon)) return null;
  return `${location.lat.toFixed(2)},${location.lon.toFixed(2)}`;
}

/** A confidence in 0-1, accepting percentages; null when unusable. */
export function unitInterval(value) {
  let n = Number(value);
  if (value === null || value === undefined || !Number.isFinite(n)) return null;
  if (n > 1) n /= 100;
  return n >= 0 && n <= 1 ? n : null;
}

/** YYYY-MM-DD from a date or date-time string, or null. */
export function toDate(value) {
  if (!value) return null;
  const match = /^(\d{4}-\d{2}-\d{2})/.exec(String(value));
  if (!match) return null;
  return Number.isNaN(Date.parse(`${match[1]}T00:00:00Z`)) ? null : match[1];
}

export function toNumber(value) {
  if (value === null || value === undefined || value === '') return null;
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

export function isObject(value) {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

// ── structured rows the farmer acts on ──────────────────────────────────────

export function irrigationRows(advice) {
  if (!isObject(advice)) return [];
  const schedule = advice.irrigation_schedule || advice.schedule || [];
  const version = String(advice.agent_version || 'unknown').slice(0, 20);
  const rows = [];
  for (const day of Array.isArray(schedule) ? schedule : []) {
    if (!isObject(day)) continue;
    const planDate = toDate(day.date);
    if (!planDate) continue;
    const depth = toNumber(day.water_depth_mm);
    const hours = toNumber(day.duration_hours);
    rows.push({
      plan_date: planDate,
      crop: advice.crop ?? null,
      growth_stage: advice.growth_stage ?? null,
      decision: String(day.decision_code || day.decision
        || (day.irrigation_required ? 'IRRIGATE' : 'SKIP')).slice(0, 40),
      // An impossible value is dropped rather than failing the run on a check.
      water_depth_mm: depth !== null && depth >= 0 && depth <= 500 ? depth : null,
      duration_hours: hours !== null && hours >= 0 && hours < 1000 ? hours : null,
      method: day.method ?? null,
      plan: day,
      agent_version: version,
    });
  }
  return rows;
}

export function cropRow(prediction) {
  if (!isObject(prediction)) return null;
  const block = isObject(prediction.result) ? prediction.result : prediction;
  const recommendations = Array.isArray(block.recommendations) ? block.recommendations : [];
  if (!recommendations.length) return null;
  const top = isObject(recommendations[0]) ? recommendations[0] : {};
  return {
    input_data: block.inputs ?? null,
    recommendations: { recommendations },
    top_crop: top.crop || top.crop_name || null,
    confidence: unitInterval(top.confidence),
    agent_version: String(prediction.agent_version || 'unknown').slice(0, 20),
    season: block.season ?? null,
  };
}

export function taskPlan(plan) {
  if (!isObject(plan) || !Array.isArray(plan.all_tasks)) return null;
  const header = { ...plan };
  for (const key of [...DERIVED_TASK_FIELDS, 'all_tasks']) delete header[key];
  const tasks = [];
  for (const task of plan.all_tasks) {
    if (!isObject(task) || !task.title) continue;
    const priority = String(task.priority || 'medium');
    const status = String(task.status || 'scheduled');
    const detail = {};
    for (const key of ['do', 'do_not', 'safety', 'cost_of_delay', 'blocked_by']) {
      if (task[key]) detail[key] = task[key];
    }
    const minutes = Math.trunc(toNumber(task.duration_minutes) ?? 60);
    const start = /^\d{2}:\d{2}$/.test(task.scheduled_start_time || '') ? task.scheduled_start_time : null;
    tasks.push({
      title: String(task.title).slice(0, 200),
      category: String(task.category || 'other').slice(0, 40),
      priority: PRIORITIES.has(priority) ? priority : 'medium',
      status: TASK_STATUSES.has(status) ? status : 'scheduled',
      scheduled_date: toDate(task.scheduled_date),
      scheduled_start_time: start,
      duration_minutes: minutes > 0 ? minutes : 60,
      why_now: task.why_now ?? null,
      detail: Object.keys(detail).length ? detail : null,
    });
  }
  return {
    plan_date: toDate(plan.generated_at),
    horizon_days: Math.trunc(toNumber(plan.planning_horizon_days) ?? 3) || 3,
    headline: plan.headline ?? null,
    summary: plan.summary ?? null,
    plan: header,
    agent_version: String(plan.agent_version || 'unknown').slice(0, 20),
    tasks,
  };
}
