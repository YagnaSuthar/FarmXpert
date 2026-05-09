// ============================================================
// FILE: components/animation/utils/generateSphere.js
//
// Generates evenly distributed particle positions on the
// surface of a sphere using the Fibonacci / golden-angle
// spiral method (much more uniform than naive random sampling).
//
// Returns a Float32Array of [x, y, z, x, y, z, …] positions.
// ============================================================

/**
 * Distributes `count` points evenly over a sphere surface
 * using the Fibonacci lattice (golden-angle spiral).
 *
 * @param {number} count  - Total number of particles (default 10 000)
 * @param {number} radius - Sphere radius in world units (default 2.0)
 * @param {number} depth  - Max Z jitter for slight volume feel (default 0.0)
 * @returns {Float32Array} Flat [x,y,z …] position buffer
 */
export function generateSphere(
  count  = 10_000,
  radius = 2.0,
  depth  = 0.0,
) {
  const positions = new Float32Array(count * 3);

  // Golden angle in radians — ensures no two consecutive
  // samples share the same azimuth band.
  const goldenAngle = Math.PI * (3 - Math.sqrt(5));

  for (let i = 0; i < count; i++) {
    // Map index to y in [-1, 1] (latitude)
    const y = 1 - (i / (count - 1)) * 2;

    // Radius at this latitude slice
    const r = Math.sqrt(Math.max(0, 1 - y * y));

    // Azimuth angle steps by the golden angle each sample
    const theta = goldenAngle * i;

    const x = Math.cos(theta) * r;
    const z = Math.sin(theta) * r;

    const base = i * 3;
    positions[base]     = x * radius;
    positions[base + 1] = y * radius;
    positions[base + 2] = z * radius + (Math.random() - 0.5) * depth;
  }

  return positions;
}

export default generateSphere;