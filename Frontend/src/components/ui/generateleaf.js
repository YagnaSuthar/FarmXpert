// ============================================================
// FILE: components/animation/utils/generateLeaf.js
//
// Constructs an organic leaf silhouette from pure parametric math.
//
// Shape anatomy
// ──────────────
//           ╱╲
//          ╱  ╲
//    tip→ ●    ●  ← widest mid-section
//          ╲  ╱
//           ╲╱  ← base / stem pinch
//            |   ← optional centre stem line
//
// The outline is driven by a "lens" / vesica curve bent with a
// quadratic bias so one end is rounder (top) and one is sharper
// (base), mimicking a real leaf.
//
// Asymmetry is introduced by a mild lateral sinusoidal warp so
// the shape leans slightly instead of being perfectly symmetric.
//
// Particles are sampled:
//   85 % → uniformly inside the leaf body
//   15 % → along the centre midrib (stem line)
// ============================================================

const TWO_PI = Math.PI * 2;

// ── Helpers ──────────────────────────────────────────────────

/**
 * Returns the half-width of the leaf at normalised height t ∈ [0,1].
 *
 * The profile uses a beta-distribution-like curve:
 *   halfWidth(t) = maxWidth * t^alpha * (1-t)^beta
 * normalised so the peak is 1.
 *
 * alpha < beta  → widest point shifted toward the top (rounder tip).
 * alpha > beta  → widest point toward the base.
 */
function leafHalfWidth(t, maxWidth, alpha = 0.7, beta = 1.4) {
  // Beta-like profile (unnormalised)
  const raw  = Math.pow(t, alpha) * Math.pow(1 - t, beta);

  // Normalise: peak of t^a*(1-t)^b is at t* = a/(a+b)
  const tPeak = alpha / (alpha + beta);
  const peak  = Math.pow(tPeak, alpha) * Math.pow(1 - tPeak, beta);

  return maxWidth * (raw / peak);
}

/**
 * Lateral (X-axis) warp applied to the entire shape to simulate
 * the natural curl / lean of a real leaf.
 *   bend ∈ [-0.5, 0.5]  reasonable range
 */
function bendWarp(t, bend) {
  // A gentle sine arch: zero at tips, maximum at mid
  return bend * Math.sin(Math.PI * t);
}

// ─────────────────────────────────────────────────────────────
// generateLeaf
// ─────────────────────────────────────────────────────────────

/**
 * @param {number} count     - Total particle count (must match other shapes)
 * @param {number} scale     - Overall size scalar (default 2.0)
 * @param {number} depth     - Z jitter magnitude (default 0.06)
 * @param {number} bend      - Lateral lean amount (default 0.18)
 * @param {number} alpha     - Top-end roundness exponent (default 0.7)
 * @param {number} beta      - Base-end taper exponent (default 1.4)
 * @returns {Float32Array}   Flat [x,y,z …] position buffer
 */
export function generateLeaf(
  count = 10_000,
  scale = 2.0,
  depth = 0.06,
  bend  = 0.18,
  alpha = 0.7,
  beta  = 1.4,
) {
  const positions = new Float32Array(count * 3);

  const maxHalfWidth = 0.45; // maximum leaf half-width at widest point

  const bodyCount  = Math.round(count * 0.85);
  const stemCount  = count - bodyCount;

  // ── 1. Leaf body particles ────────────────────────────────
  // For each particle we:
  //   a) pick a random height t ∈ [0,1]  (0=base, 1=tip)
  //   b) compute the max half-width at that height
  //   c) pick a random x within [-halfW, +halfW]
  //   d) apply the bend warp to x

  for (let i = 0; i < bodyCount; i++) {
    const t    = Math.random();               // normalised height
    const halfW = leafHalfWidth(t, maxHalfWidth, alpha, beta);

    // Uniform sample across the width slice
    const xLocal = (Math.random() * 2 - 1) * halfW;

    // Y: map t from [0,1] → [-0.5, 0.5] (centred, tip at top)
    const y = t - 0.5;

    // Apply lateral bend based on height
    const x = xLocal + bendWarp(t, bend);

    // Mild Z depth — thicker in the middle, flat at edges
    const zScale = 1 - Math.abs(xLocal / (maxHalfWidth + 1e-6));
    const z = (Math.random() - 0.5) * depth * zScale;

    const base = i * 3;
    positions[base]     = x;
    positions[base + 1] = y;
    positions[base + 2] = z;
  }

  // ── 2. Centre midrib (stem line) ──────────────────────────
  // A slightly curved line from base to tip, offset by bend.
  // This accentuates the leafy silhouette in close-up views.

  for (let i = 0; i < stemCount; i++) {
    const t  = Math.random();
    const y  = t - 0.5;
    const x  = bendWarp(t, bend * 0.6) + (Math.random() - 0.5) * 0.012;
    const z  = (Math.random() - 0.5) * depth * 0.3;

    const base = (bodyCount + i) * 3;
    positions[base]     = x;
    positions[base + 1] = y;
    positions[base + 2] = z;
  }

  // ── 3. Apply uniform scale ────────────────────────────────
  for (let i = 0; i < count; i++) {
    const base = i * 3;
    positions[base]     *= scale;
    positions[base + 1] *= scale;
    positions[base + 2] *= scale;
  }

  return positions;
}

export default generateLeaf;