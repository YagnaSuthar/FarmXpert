// ============================================================
// FILE: src/reusablefiles/pagetransition/field.geometry.js
//
// Geometry for the transition stage.
//
// Everything is DETERMINISTIC — one seeded PRNG, no Math.random — so the
// server and client emit identical markup and hydration never mismatches.
// It runs once at module scope, so a route change costs nothing.
//
// Two shapes carry the whole composition:
//
//   RIBBONS. Long S-curves that enter off one edge and leave off another,
//   so the frame is a crop of something larger. Control points are pushed
//   perpendicular to the chord, which is what makes a curve sweep rather
//   than sag. Each is stroked with a gradient that fades at both ends, so
//   a ribbon has no visible start or stop — it just passes through.
//
//   MOTES. Points of light rising slowly at three depths. Size, opacity
//   and speed all read off one z value, which is what reads as air
//   between them rather than as dots on glass.
// ============================================================

import { STAGE_CENTER } from './transition.config';

export const STAGE_W = 1600;
export const STAGE_H = 900;

/** Deterministic PRNG (mulberry32). */
function seeded(seed) {
  let s = seed | 0;
  return () => {
    s = (s + 0x6d2b79f5) | 0;
    let t = Math.imul(s ^ (s >>> 15), 1 | s);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const rnd = seeded(0x1f2e3d4c);
const range = (a, b) => a + rnd() * (b - a);

/* ----------------------------------------------------------- ribbons */

/**
 * A ribbon runs from well outside one edge to well outside another. The
 * two control points are offset along the chord's normal in OPPOSITE
 * directions, which produces a long lazy S instead of a single bulge.
 */
function makeRibbon(i, total) {
  // spread entry heights across the frame, with jitter so they never band
  const lead = i / (total - 1);
  const x1 = -320;
  const y1 = range(-160, STAGE_H + 160) * 0.45 + lead * STAGE_H * 0.75;
  const x2 = STAGE_W + 320;
  const y2 = range(-160, STAGE_H + 160) * 0.45 + (1 - lead) * STAGE_H * 0.75;

  const dx = x2 - x1;
  const dy = y2 - y1;
  const len = Math.hypot(dx, dy) || 1;
  const nx = -dy / len;
  const ny = dx / len;

  const bow = range(150, 420);
  const c1x = x1 + dx * 0.3 + nx * bow;
  const c1y = y1 + dy * 0.3 + ny * bow;
  const c2x = x1 + dx * 0.7 - nx * bow * range(0.6, 1.1);
  const c2y = y1 + dy * 0.7 - ny * bow * range(0.6, 1.1);

  const z = range(0.18, 1);

  return {
    d: `M ${x1} ${y1.toFixed(1)} C ${c1x.toFixed(1)} ${c1y.toFixed(1)}, ${c2x.toFixed(1)} ${c2y.toFixed(1)}, ${x2} ${y2.toFixed(1)}`,
    z,
    width: 0.8 + z * 3.2,
    opacity: 0.1 + z * 0.4,
    delay: 120 + i * 130,
    dur: 1800 + z * 1400,
    driftDur: 14 + rnd() * 12,
    driftDelay: -rnd() * 12,
  };
}

export const RIBBONS = Array.from({ length: 9 }, (_, i) => makeRibbon(i, 9));

/* ------------------------------------------------------------- motes */

/**
 * Points of light rising. Seeded below the frame as well as inside it,
 * so the field is already in motion when the transition opens rather
 * than starting from an empty screen.
 */
export const MOTES = Array.from({ length: 26 }, (_, i) => {
  const z = range(0.15, 1);
  return {
    x: range(-40, STAGE_W + 40),
    y: range(-60, STAGE_H + 220),
    r: 0.9 + z * 3.4,
    opacity: 0.12 + z * 0.62,
    rise: 160 + z * 420,
    dur: 9 + (1 - z) * 12,
    delay: -rnd() * 14,
    twinkleDur: 2.4 + rnd() * 3.4,
    key: i,
  };
});

/* ------------------------------------------------------------- rings */

/**
 * Light blooming out of the centre. Radii are unbounded on purpose — the
 * last ring is wider than the frame, so the bloom leaves the screen
 * instead of stopping politely inside it.
 */
export const RINGS = Array.from({ length: 4 }, (_, i) => ({
  key: i,
  delay: i * 1.15,
  dur: 4.6,
}));

export const CENTER = STAGE_CENTER;
