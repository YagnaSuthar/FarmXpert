// ============================================================
// FILE: src/services/dashboard.service.js
//
// Data layer for the dashboard. Two jobs:
//
//   1. Talk to the API through the shared `@/lib/api` client.
//   2. Shape whatever comes back into the exact structures the chart
//      components expect, so pages stay declarative.
//
// Where the backend already exposes data (the user directory, the
// manager summary) the numbers are DERIVED FROM IT — role mix, signup
// history and verification rate are all computed from real rows.
//
// The farm telemetry endpoints do not exist on the backend yet. Rather
// than render an empty dashboard, `fetchFarmTelemetry` tries the API
// first and falls back to a SEEDED sample so the layout stays legible;
// the fallback is flagged as `simulated: true` so the UI can say so.
// ============================================================

import api from '@/lib/api';

/* ------------------------------------------------------------ utils */

/** Deterministic PRNG — same seed, same series, every render. */
function seeded(seed) {
  let s = seed | 0;
  return () => {
    s |= 0;
    s = (s + 0x6d2b79f5) | 0;
    let t = Math.imul(s ^ (s >>> 15), 1 | s);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/**
 * Smooth-ish random walk inside [min, max]. The pull back toward the
 * midpoint keeps the series from drifting into a rail and flattening —
 * an unbiased walk hits the ceiling within a handful of steps.
 */
function walkSeries(seed, count, min, max) {
  const rnd = seeded(seed);
  const span = max - min;
  const mid = (min + max) / 2;
  const out = [];
  let v = min + span * rnd();
  for (let i = 0; i < count; i++) {
    v += (rnd() - 0.5) * span * 0.5 + (mid - v) * 0.2;
    v = Math.min(max, Math.max(min, v));
    out.push(Math.round(v * 10) / 10);
  }
  return out;
}

/** Month index list ending on the current month, oldest first. */
export function lastMonths(count = 6, now = new Date()) {
  const out = [];
  for (let i = count - 1; i >= 0; i--) {
    const d = new Date(now.getFullYear(), now.getMonth() - i, 1);
    out.push({ year: d.getFullYear(), month: d.getMonth() });
  }
  return out;
}

/* ------------------------------------------------------- API calls */

/**
 * Platform user directory (admin + super-admin).
 * @returns {Promise<{ users: object[], error: string|null }>}
 */
export async function fetchUsers() {
  try {
    const res = await api.get('/auth/admin/users');
    if (res.success && Array.isArray(res.data?.users)) {
      return { users: res.data.users, error: null };
    }
    return { users: [], error: null };
  } catch (err) {
    return { users: [], error: err?.message || 'Failed to load users' };
  }
}

/** Manager operations summary. */
export async function fetchManagerSummary() {
  try {
    const res = await api.get('/auth/manager/dashboard');
    if (res.success && res.data) return { summary: res.data, error: null };
    return { summary: null, error: null };
  } catch (err) {
    return { summary: null, error: err?.message || 'Failed to load summary' };
  }
}

/** Change a user's role. Never accepts `super_admin` — that is provisioned server-side. */
export async function updateUserRole(userId, role) {
  if (!['user', 'manager', 'admin'].includes(role)) {
    throw new Error('Unsupported role');
  }
  return api.patch(`/auth/admin/users/${userId}/role`, { role });
}

/* --------------------------------------------- derived directory metrics */

export const ROLE_KEYS = ['user', 'manager', 'admin', 'super_admin'];

/**
 * Everything the admin / super-admin charts need, computed from the
 * real user rows — no invented numbers.
 *
 * @param {object[]} users
 * @param {Date} [now]
 */
export function buildDirectoryMetrics(users = [], now = new Date()) {
  const total = users.length;
  const verified = users.filter((u) => u.email_verified).length;
  const pending = total - verified;

  const byRole = ROLE_KEYS.map((role) => ({
    role,
    value: users.filter((u) => u.role === role).length,
  }));

  const months = lastMonths(6, now);
  const signups = months.map(({ year, month }) =>
    users.filter((u) => {
      if (!u.created_at) return false;
      const d = new Date(u.created_at);
      return d.getFullYear() === year && d.getMonth() === month;
    }).length,
  );

  const verifiedByMonth = months.map(({ year, month }) =>
    users.filter((u) => {
      if (!u.created_at || !u.email_verified) return false;
      const d = new Date(u.created_at);
      return d.getFullYear() === year && d.getMonth() === month;
    }).length,
  );

  // A box plot needs a distribution: account age in days, per role.
  const ageDays = (u) =>
    u.created_at ? Math.max(0, (now - new Date(u.created_at)) / 86400000) : null;

  const ageByRole = ROLE_KEYS.map((role) => ({
    role,
    values: users
      .filter((u) => u.role === role)
      .map(ageDays)
      .filter((v) => v != null),
  })).filter((g) => g.values.length);

  return {
    total,
    verified,
    pending,
    verificationRate: total ? Math.round((verified / total) * 100) : 0,
    byRole,
    months,
    signups,
    verifiedByMonth,
    newestThisMonth: signups[signups.length - 1] || 0,
    ageByRole,
  };
}

/* ------------------------------------------------- farm telemetry */

/**
 * Field telemetry for the farmer / manager dashboards.
 *
 * Tries the API first. When the endpoint is not available (it is not
 * implemented on the backend yet) it returns a seeded sample marked
 * `simulated: true` so the page can label it honestly instead of
 * presenting placeholder numbers as live readings.
 *
 * @param {string} scope 'farm' | 'operations'
 */
export async function fetchFarmTelemetry(scope = 'farm') {
  try {
    const res = await api.get(`/telemetry/${scope}`);
    if (res.success && res.data) return { ...res.data, simulated: false, error: null };
  } catch {
    // endpoint absent or unauthorized — fall through to the sample
  }
  return { ...buildSampleTelemetry(scope), simulated: true, error: null };
}

/** Seeded stand-in dataset shaped exactly like the live payload. */
export function buildSampleTelemetry(scope = 'farm') {
  const isOps = scope === 'operations';
  const base = isOps ? 0x3f2a91 : 0x9c14ab;

  return {
    scope,
    /* headline metrics */
    stats: {
      nodes: isOps ? 256 : 18,
      nodesTrend: isOps ? 6 : 12,
      moisture: 42,
      moistureTrend: -3,
      temperature: 24.2,
      temperatureTrend: 2,
      health: isOps ? 94 : 87,
      healthTrend: 5,
      uptime: 99.2,
      latency: isOps ? 184 : 96,
    },

    /* 6-month trend, used by the bar / line charts */
    months: walkSeries(base, 6, 35, 92).map((v) => Math.round(v)),

    /* 6-month multi-series, used by the grouped / stacked bars */
    monthly: {
      synced: walkSeries(base + 61, 6, 40, 90).map((v) => Math.round(v)),
      syncing: walkSeries(base + 73, 6, 10, 38).map((v) => Math.round(v)),
      offline: walkSeries(base + 87, 6, 2, 20).map((v) => Math.round(v)),
    },

    /* 7-day series for the line chart */
    week: {
      moisture: walkSeries(base + 11, 7, 28, 58).map((v) => Math.round(v)),
      temperature: walkSeries(base + 23, 7, 18, 32),
    },

    /* composition for the semi-circular gauge */
    progress: isOps
      ? [
          { key: 'synced', value: 58 },
          { key: 'syncing', value: 24 },
          { key: 'offline', value: 18 },
        ]
      : [
          { key: 'harvested', value: 41 },
          { key: 'growing', value: 37 },
          { key: 'planned', value: 22 },
        ],

    /* radial rings */
    rings: [
      { key: 'soil', value: 78 },
      { key: 'water', value: 64 },
      { key: 'nutrient', value: 52 },
    ],

    /* distribution per zone for the box plot */
    zones: ['A', 'B', 'C', 'D'].map((zone, i) => ({
      zone,
      values: walkSeries(base + 40 + i * 7, 24, 24 + i * 3, 62 - i * 2),
    })),

    /* radar comparison */
    radar: {
      axes: ['soil', 'water', 'nutrient', 'pest', 'yield', 'canopy'],
      current: [78, 64, 52, 88, 71, 66],
      target: [85, 75, 70, 90, 80, 75],
    },

    /* hour x weekday activity for the heat map */
    activity: Array.from({ length: 7 }, (_, r) =>
      walkSeries(base + 200 + r * 13, 12, 0, 100).map((v) => Math.round(v)),
    ),

    /* scatter: moisture vs yield per plot */
    plots: Array.from({ length: 14 }, (_, i) => {
      const rnd = seeded(base + 900 + i);
      const x = 26 + rnd() * 34;
      return {
        label: `P${i + 1}`,
        x: Math.round(x * 10) / 10,
        y: Math.round((1.6 + (x - 26) * 0.11 + rnd() * 0.8) * 10) / 10,
        r: Math.round(2 + rnd() * 10),
      };
    }),

    /* field / deployment rows */
    items: isOps
      ? [
          { key: 'northSensors', value: 128, progress: 92 },
          { key: 'westGateways', value: 46, progress: 78 },
          { key: 'pestTraps', value: 82, progress: 64 },
          { key: 'weatherMasts', value: 12, progress: 88 },
        ]
      : [
          { key: 'soilProbe', value: 42, progress: 42 },
          { key: 'npk', value: 142, progress: 71 },
          { key: 'canopyTemp', value: 24.2, progress: 55 },
          { key: 'pestRisk', value: 4, progress: 4 },
        ],

    trackerSeconds: 1 * 3600 + 24 * 60 + 8,
  };
}
