// FILE: components/animation/shapes/generateLeaf.js
// ============================================================
// Generates particle positions for a 3D leaf shape.
// Represents Soil, Crop, Growth, etc.
// ============================================================

export function generateLeaf(particleCount, radius = 5) {
  const positions = new Float32Array(particleCount * 3);

  for (let i = 0; i < particleCount; i++) {
    // Generate points on a curved leaf surface using parametric equations
    
    // U and V parameters
    const u = Math.random();
    const v = Math.random();

    // Leaf outline (parametric teardrop/leaf shape)
    // Map u from 0 to 1 -> angle from 0 to 2*PI (or 0 to PI and reflect)
    const angle = u * Math.PI;
    
    // Equation for leaf shape width at a given height (v)
    // v goes from 0 (base) to 1 (tip)
    const widthAtV = Math.sin(v * Math.PI) * (1 - v) * 2.5; 
    
    // Randomly place point within the width
    const x = (Math.random() * 2 - 1) * widthAtV * radius;
    
    // Y is the length of the leaf
    const y = (v * 2 - 1) * radius;
    
    // Z creates a slight curve (cupping) along the leaf
    const zCurve = -Math.pow(x / radius, 2) * radius * 0.5 + Math.sin(v * Math.PI) * radius * 0.2;
    // Add small random noise to Z for thickness
    const z = zCurve + (Math.random() * 0.4 - 0.2);

    const i3 = i * 3;
    positions[i3] = x;
    positions[i3 + 1] = y;
    positions[i3 + 2] = z;
  }

  return positions;
}
