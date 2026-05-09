// FILE: components/animation/shapes/generateSphere.js
// ============================================================
// Generates particle positions for a 3D Sphere shape.
// This is the default idle state for the central core.
// ============================================================

export function generateSphere(particleCount, radius = 5) {
  const positions = new Float32Array(particleCount * 3);

  for (let i = 0; i < particleCount; i++) {
    // Generate uniform points on a sphere surface using math
    const u = Math.random();
    const v = Math.random();
    
    const theta = u * 2.0 * Math.PI;
    const phi = Math.acos(2.0 * v - 1.0);
    
    // Add volume (not just surface shell) to make it look dense
    // We want more particles near the surface, so we take the cube root
    const r = radius * Math.cbrt(Math.random() * 0.5 + 0.5);

    const x = r * Math.sin(phi) * Math.cos(theta);
    const y = r * Math.sin(phi) * Math.sin(theta);
    const z = r * Math.cos(phi);

    const i3 = i * 3;
    positions[i3] = x;
    positions[i3 + 1] = y;
    positions[i3 + 2] = z;
  }

  return positions;
}
