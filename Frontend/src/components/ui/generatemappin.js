// ============================================================
// FILE: components/animation/utils/generateMapPin.js
//
// Constructs a map-pin / teardrop silhouette from pure math:
//
//   ┌─────────────────────────────────────────────────────┐
//   │          ●●●●●●●●●●●                                │
//   │       ●●●●●●●●●●●●●●●●●                             │
//   │     ●●●●●●●●●●●●●●●●●●●●●   ← filled circle head   │
//   │       ●●●●●●●●●●●●●●●●●                             │
//   │          ●●●●●●●●●●●                                │
//   │            ●●●●●●●                                  │
//   │              ●●●●    ← tapered neck                 │
//   │               ●●                                    │
//   │                ●     ← sharp bottom tip             │
//   └─────────────────────────────────────────────────────┘
//
// Strategy
// ─────────
//   60 % of particles → filled circle (head)
//   40 % of particles → tapered teardrop tail
//
// All positions are centred on (0,0,0) and normalised to a
// uniform bounding scale so morphing from other shapes is smooth.
// ============================================================

const TWO_PI = Math.PI * 2;

// ── Helpers ──────────────────────────────────────────────────

/**
 * Samples a 2-D point uniformly inside a circle of given radius.
 * Uses polar-area correction (sqrt of u) so density is even.
 */
function sampleDisk(radius) {
  const r     = radius * Math.sqrt(Math.random());
  const theta = Math.random() * TWO_PI;
  return [Math.cos(theta) * r, Math.sin(theta) * r];
}

/**
 * Samples a point inside the teardrop tail section.
 *
 * The tail is modelled as a parametric shape where:
 *   • t ∈ [0, 1]  runs from the bottom of the head to the tip
 *   • width at t  = tailMaxWidth * (1 - t)^exponent
 *   • y at t      = tailTop - t * tailHeight
 *
 * A small amount of uniform noise is added so particles don't
 * cluster on the centre axis.
 */
function sampleTail(t, tailTop, tailHeight, tailMaxWidth, exponent = 1.4) {
  const halfW = tailMaxWidth * Math.pow(1 - t, exponent);
  const x     = (Math.random() * 2 - 1) * halfW;
  const y     = tailTop - t * tailHeight;
  return [x, y];
}

// ─────────────────────────────────────────────────────────────
// generateMapPin
// ─────────────────────────────────────────────────────────────

/**
 * @param {number} count  - Total particle count (must match other shapes)
 * @param {number} scale  - Overall size scalar (default 2.0)
 * @param {number} depth  - Z jitter for slight 3-D feel (default 0.08)
 * @returns {Float32Array} Flat [x,y,z …] position buffer
 */
export function generateMapPin(
  count = 10_000,
  scale = 2.0,
  depth = 0.08,
) {
  const positions = new Float32Array(count * 3);

  // ── Geometry parameters (in normalised units, scaled at the end) ──
  const headRadius   = 0.55;   // radius of the circular head
  const headCentreY  = 0.30;   // Y offset of head centre (above origin)
  const tailTop      = headCentreY - headRadius * 0.75; // where tail starts
  const tailHeight   = 1.10;   // how far the tail descends
  const tailMaxWidth = headRadius * 0.52; // widest point of the tail

  // Fraction split
  const headCount = Math.round(count * 0.60);
  const tailCount = count - headCount;

  // ── 1. Fill the circular head ────────────────────────────────
  for (let i = 0; i < headCount; i++) {
    const [x, y] = sampleDisk(headRadius);
    const base   = i * 3;
    positions[base]     = x;
    positions[base + 1] = y + headCentreY;
    positions[base + 2] = (Math.random() - 0.5) * depth;
  }

  // ── 2. Fill the teardrop tail ────────────────────────────────
  for (let i = 0; i < tailCount; i++) {
    // Bias sampling toward top of tail (more particles near head join)
    // using a sqrt distribution so the density gradient looks natural.
    const t          = Math.pow(Math.random(), 0.75);
    const [x, y]     = sampleTail(t, tailTop, tailHeight, tailMaxWidth);
    const base       = (headCount + i) * 3;
    positions[base]     = x;
    positions[base + 1] = y;
    positions[base + 2] = (Math.random() - 0.5) * depth * (1 - t); // tip is flat
  }

  // ── 3. Centre on Y axis & apply scale ────────────────────────
  // Find bounding box to re-centre vertically
  let minY = Infinity;
  let maxY = -Infinity;
  for (let i = 0; i < count; i++) {
    const y = positions[i * 3 + 1];
    if (y < minY) minY = y;
    if (y > maxY) maxY = y;
  }
  const centreOffsetY = (maxY + minY) / 2;

  for (let i = 0; i < count; i++) {
    const base = i * 3;
    positions[base]     *= scale;
    positions[base + 1]  = (positions[base + 1] - centreOffsetY) * scale;
    positions[base + 2] *= scale;
  }

  return positions;
}

export default generateMapPin;