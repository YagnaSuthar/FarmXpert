// ============================================================
// FILE: src/reusablefiles/graphs/chart.utils.js
//
// Shared geometry / scale / formatting helpers for every chart in
// this folder. Pure functions only — no React, no DOM, no deps.
//
// COLOR RULE: charts never hold a literal color. They reference the
// Frozen Lake ramp declared in globals.css (`--graph-series-*`) via
// the SERIES token list below and hand it to SVG through `style`
// (presentation attributes do not resolve `var()` reliably).
// ============================================================

/** Ordered categorical ramp — every token lives in globals.css :root. */
export const SERIES = [
  'var(--graph-series-1)',
  'var(--graph-series-2)',
  'var(--graph-series-3)',
  'var(--graph-series-4)',
  'var(--graph-series-5)',
  'var(--graph-series-6)',
  'var(--graph-series-7)',
  'var(--graph-series-8)',
];

/** Pick a ramp color by index, wrapping around the ramp length. */
export const seriesColor = (i, ramp = SERIES) => ramp[i % ramp.length];

/* ---------------------------------------------------------------- math */

export const clamp = (v, min, max) => Math.min(max, Math.max(min, v));

export const sum = (arr) => arr.reduce((a, b) => a + b, 0);

/** Round to at most `p` decimals (keeps emitted path strings short). */
export const round = (n, p = 2) => Number.parseFloat(Number(n).toFixed(p));

/**
 * Linear scale factory.
 * @param {[number, number]} domain input range
 * @param {[number, number]} range  output range (user units)
 */
export function scaleLinear([d0, d1], [r0, r1]) {
  const span = d1 - d0 || 1;
  const fn = (v) => r0 + ((v - d0) / span) * (r1 - r0);
  fn.invert = (px) => d0 + ((px - r0) / (r1 - r0 || 1)) * span;
  return fn;
}

/**
 * Evenly spaced band positions (bar-style charts).
 * @returns {{ step:number, band:number, at:(i:number)=>number }}
 */
export function scaleBand(count, [r0, r1], padding = 0.32) {
  const step = (r1 - r0) / Math.max(1, count);
  const band = step * (1 - padding);
  return { step, band, at: (i) => r0 + i * step + (step - band) / 2 };
}

/**
 * "Nice" axis ticks — rounded to 1 / 2 / 2.5 / 5 x 10^n steps so labels
 * read as human numbers instead of 37.428.
 */
export function niceTicks(min, max, count = 5) {
  if (!Number.isFinite(min) || !Number.isFinite(max)) {
    return { ticks: [0, 1], min: 0, max: 1 };
  }
  let lowIn = min;
  let highIn = max;
  if (lowIn === highIn) {
    const pad = Math.abs(lowIn) || 1;
    lowIn -= pad;
    highIn += pad;
  }
  const raw = (highIn - lowIn) / Math.max(1, count);
  const mag = Math.pow(10, Math.floor(Math.log10(raw)));
  const norm = raw / mag;
  const step = (norm >= 5 ? 10 : norm >= 2.5 ? 5 : norm >= 2 ? 2.5 : norm >= 1 ? 2 : 1) * mag;
  const lo = Math.floor(lowIn / step) * step;
  const hi = Math.ceil(highIn / step) * step;
  const ticks = [];
  for (let v = lo; v <= hi + step * 1e-6; v += step) ticks.push(round(v, 6));
  return { ticks, min: lo, max: hi };
}

/* ------------------------------------------------------------- paths */

/**
 * Polyline through points. `curve: 'linear' | 'smooth' | 'step'`.
 * `smooth` emits real cubic beziers from a Catmull-Rom spline, so the
 * line stays smooth at any render size instead of faceting.
 */
export function linePath(points, curve = 'linear') {
  if (!points.length) return '';
  if (points.length === 1) return `M ${round(points[0][0])} ${round(points[0][1])}`;

  const move = `M ${round(points[0][0])} ${round(points[0][1])}`;

  if (curve === 'step') {
    return move + points.slice(1).map(([x, y], i) => {
      const mx = round((points[i][0] + x) / 2);
      return ` L ${mx} ${round(points[i][1])} L ${mx} ${round(y)} L ${round(x)} ${round(y)}`;
    }).join('');
  }

  if (curve === 'smooth') {
    let d = move;
    for (let i = 0; i < points.length - 1; i++) {
      const p0 = points[i - 1] || points[i];
      const p1 = points[i];
      const p2 = points[i + 1];
      const p3 = points[i + 2] || p2;
      const c1x = p1[0] + (p2[0] - p0[0]) / 6;
      const c1y = p1[1] + (p2[1] - p0[1]) / 6;
      const c2x = p2[0] - (p3[0] - p1[0]) / 6;
      const c2y = p2[1] - (p3[1] - p1[1]) / 6;
      d += ` C ${round(c1x)} ${round(c1y)}, ${round(c2x)} ${round(c2y)}, ${round(p2[0])} ${round(p2[1])}`;
    }
    return d;
  }

  return move + points.slice(1).map(([x, y]) => ` L ${round(x)} ${round(y)}`).join('');
}

/** Closed area under a line, dropped to `baseY`. */
export function areaPath(points, baseY, curve = 'linear') {
  if (!points.length) return '';
  const top = linePath(points, curve);
  const last = points[points.length - 1];
  return `${top} L ${round(last[0])} ${round(baseY)} L ${round(points[0][0])} ${round(baseY)} Z`;
}

/**
 * Point on a circle. Angles use 0 deg = straight up, increasing
 * clockwise — far easier to reason about than SVG's native 0 = east.
 */
export function polar(cx, cy, r, deg) {
  const a = ((deg - 90) * Math.PI) / 180;
  return [cx + r * Math.cos(a), cy + r * Math.sin(a)];
}

/** Stroked arc (no fill) between two angles. */
export function arcPath(cx, cy, r, fromDeg, toDeg) {
  const delta = toDeg - fromDeg;
  if (Math.abs(delta) < 0.01) return '';
  // A full sweep cannot be expressed as a single arc — nudge the end back.
  const end = Math.abs(delta) >= 359.99 ? fromDeg + 359.99 * Math.sign(delta) : toDeg;
  const [x0, y0] = polar(cx, cy, r, fromDeg);
  const [x1, y1] = polar(cx, cy, r, end);
  const large = Math.abs(end - fromDeg) > 180 ? 1 : 0;
  const sweep = end > fromDeg ? 1 : 0;
  return `M ${round(x0)} ${round(y0)} A ${round(r)} ${round(r)} 0 ${large} ${sweep} ${round(x1)} ${round(y1)}`;
}

/** Filled ring wedge — donut / pie segments. */
export function wedgePath(cx, cy, rOuter, rInner, fromDeg, toDeg) {
  const delta = Math.abs(toDeg - fromDeg);
  if (delta < 0.01) return '';
  const end = delta >= 359.99 ? fromDeg + 359.99 : toDeg;
  const [ox0, oy0] = polar(cx, cy, rOuter, fromDeg);
  const [ox1, oy1] = polar(cx, cy, rOuter, end);
  const [ix1, iy1] = polar(cx, cy, rInner, end);
  const [ix0, iy0] = polar(cx, cy, rInner, fromDeg);
  const large = end - fromDeg > 180 ? 1 : 0;
  return [
    `M ${round(ox0)} ${round(oy0)}`,
    `A ${round(rOuter)} ${round(rOuter)} 0 ${large} 1 ${round(ox1)} ${round(oy1)}`,
    `L ${round(ix1)} ${round(iy1)}`,
    `A ${round(rInner)} ${round(rInner)} 0 ${large} 0 ${round(ix0)} ${round(iy0)}`,
    'Z',
  ].join(' ');
}

/** Bar path with the two leading corners rounded. */
export function roundedRect(x, y, w, h, r) {
  if (h <= 0 || w <= 0) return '';
  const rad = Math.min(r, w / 2, h);
  return [
    `M ${round(x)} ${round(y + h)}`,
    `L ${round(x)} ${round(y + rad)}`,
    `Q ${round(x)} ${round(y)} ${round(x + rad)} ${round(y)}`,
    `L ${round(x + w - rad)} ${round(y)}`,
    `Q ${round(x + w)} ${round(y)} ${round(x + w)} ${round(y + rad)}`,
    `L ${round(x + w)} ${round(y + h)}`,
    'Z',
  ].join(' ');
}

/* -------------------------------------------------------- statistics */

/** Linear-interpolated quantile over an ASCENDING-sorted array. */
export function quantile(sorted, q) {
  if (!sorted.length) return 0;
  const pos = (sorted.length - 1) * q;
  const base = Math.floor(pos);
  const rest = pos - base;
  const next = sorted[base + 1];
  return next === undefined ? sorted[base] : sorted[base] + rest * (next - sorted[base]);
}

/**
 * Five-number summary + Tukey fences for a box plot. Points beyond
 * 1.5 x IQR from the hinges come back separately as outliers.
 */
export function boxStats(values) {
  const clean = (values || []).filter(Number.isFinite).slice().sort((a, b) => a - b);
  if (!clean.length) return null;
  const q1 = quantile(clean, 0.25);
  const median = quantile(clean, 0.5);
  const q3 = quantile(clean, 0.75);
  const iqr = q3 - q1;
  const lo = q1 - 1.5 * iqr;
  const hi = q3 + 1.5 * iqr;
  const inliers = clean.filter((v) => v >= lo && v <= hi);
  return {
    min: clean[0],
    max: clean[clean.length - 1],
    q1,
    median,
    q3,
    iqr,
    whiskerLow: inliers.length ? inliers[0] : clean[0],
    whiskerHigh: inliers.length ? inliers[inliers.length - 1] : clean[clean.length - 1],
    outliers: clean.filter((v) => v < lo || v > hi),
    mean: sum(clean) / clean.length,
    count: clean.length,
  };
}

/* -------------------------------------------------------- formatting */

/** 1240 -> "1.2K". Locale-aware, falls back to plain digits. */
export function formatCompact(value, locale = 'en') {
  if (!Number.isFinite(value)) return '—';
  try {
    return new Intl.NumberFormat(locale, {
      notation: 'compact',
      maximumFractionDigits: 1,
    }).format(value);
  } catch {
    return String(round(value, 1));
  }
}

export function formatNumber(value, locale = 'en', options) {
  if (!Number.isFinite(value)) return '—';
  try {
    return new Intl.NumberFormat(locale, options).format(value);
  } catch {
    return String(round(value, 2));
  }
}

/** Accepts `[{label,value}]`, `[number]` or `[[label,value]]`. */
export function normalizeSeries(data = []) {
  return data
    .map((d, i) => {
      if (d == null) return null;
      if (typeof d === 'number') return { label: String(i + 1), value: d };
      if (Array.isArray(d)) return { label: String(d[0]), value: Number(d[1]) };
      return { ...d, label: d.label ?? String(i + 1), value: Number(d.value) };
    })
    .filter((d) => d && Number.isFinite(d.value));
}
