// FILE: components/animation/shapes/generateMapPin.js
// ============================================================
// Generates particle positions for a 3D Map Pin shape.
// Represents Map, Location, Tracking agents.
// ============================================================

export function generateMapPin(particleCount, radius = 4) {
  const positions = new Float32Array(particleCount * 3);

  for (let i = 0; i < particleCount; i++) {
    const r = Math.random();
    let x, y, z;

    // A map pin consists of a top sphere and a bottom cone.
    // We will distribute particles randomly between these two geometric shapes.
    
    if (r > 0.3) {
      // Top Sphere (70% of particles)
      const u = Math.random();
      const v = Math.random();
      const theta = 2 * Math.PI * u;
      // Map phi from 0 to PI (mostly upper half sphere)
      const phi = Math.acos(2 * v - 1);
      
      const sphereRadius = radius * 0.6;
      x = sphereRadius * Math.sin(phi) * Math.cos(theta);
      y = sphereRadius * Math.sin(phi) * Math.sin(theta) + radius * 0.4; // shift up
      z = sphereRadius * Math.cos(phi);
      
      // Hollow out the center slightly
      const shellThickness = 0.8 + Math.random() * 0.2;
      x *= shellThickness;
      y = (y - radius * 0.4) * shellThickness + radius * 0.4;
      z *= shellThickness;
    } else {
      // Bottom Cone (30% of particles)
      // v ranges from 0 (tip) to 1 (base of cone where it meets sphere)
      const v = Math.random(); 
      const theta = Math.random() * 2 * Math.PI;
      
      // Radius of cone at height v (matches sphere bottom)
      const coneRadiusAtV = v * (radius * 0.5); 
      
      x = coneRadiusAtV * Math.cos(theta);
      z = coneRadiusAtV * Math.sin(theta);
      // y maps from -radius (tip) to radius * 0.2 (base)
      y = -radius + (v * radius * 1.4);
      
      // Surface noise
      const shell = 0.9 + Math.random() * 0.1;
      x *= shell;
      z *= shell;
    }

    const i3 = i * 3;
    positions[i3] = x;
    positions[i3 + 1] = y;
    positions[i3 + 2] = z;
  }

  return positions;
}
