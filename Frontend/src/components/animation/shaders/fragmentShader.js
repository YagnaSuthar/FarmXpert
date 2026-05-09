const fragmentShader = `// FILE: components/animation/shaders/fragment.glsl
// ============================================================
// GPU Particle Fragment Shader — FarmXpert Green Theme
//
// Runs once per pixel INSIDE each gl_PointSize square.
// Responsible for:
//   1. Circular mask   — discard corners of point quad
//   2. Soft glow core  — multi-layer radial falloff
//   3. Energy ring     — thin bright rim on hover
//   4. Chromatic tint  — green-themed from varyings
//   5. Premultiplied α — correct for additive blend mode
// ============================================================

precision highp float;

// ── Uniforms ─────────────────────────────────────────────────
uniform float uTime;
uniform float uHover;
uniform float uTheme;

// ── Varyings from vertex ──────────────────────────────────────
varying float vAlpha;
varying float vGlow;
varying vec3  vColor;

// ─────────────────────────────────────────────────────────────
// RADIAL HELPERS
// ─────────────────────────────────────────────────────────────

float pointDist() {
  return length(gl_PointCoord - 0.5);
}

float circleMask(float d, float softness) {
  return 1.0 - smoothstep(0.5 - softness, 0.5, d);
}

// ─────────────────────────────────────────────────────────────
// GLOW LAYERS
// ─────────────────────────────────────────────────────────────

float glowCore(float d) {
  return exp(-d * 24.0);
}

float glowMid(float d) {
  return exp(-d * 8.0) * 0.6;
}

float glowOuter(float d) {
  return exp(-d * 3.5) * 0.28;
}

// ─────────────────────────────────────────────────────────────
// ENERGY RING
// ─────────────────────────────────────────────────────────────
float energyRing(float d, float time, float hover) {
  float ringRadius = 0.15 + 0.27 * abs(sin(time * 2.2));
  float ringWidth  = 0.04;
  float ring       = exp(-pow((d - ringRadius) / ringWidth, 2.0));
  return ring * 0.8 * hover;
}

// ─────────────────────────────────────────────────────────────
// MAIN
// ─────────────────────────────────────────────────────────────
void main() {

  float d = pointDist();

  if (d > 0.5) discard;

  float mask = circleMask(d, 0.08);

  // Multi-layer glow — softened falloffs for bigger particles
  float glow =
      glowCore(d)    * (1.0 + vGlow * 1.6)
    + glowMid(d)     * (0.9 + vGlow * 0.6)
    + glowOuter(d)   * (0.7 + vGlow * 0.4);

  float ring = energyRing(d, uTime, uHover);
  glow += ring;

  // GREEN theme colour construction (Dark Mode)
  float rimHeat  = 1.0 - smoothstep(0.1, 0.4, d);
  vec3  warmTintGreen = vec3(0.50, 1.00, 0.60);          // green-warm rim
  vec3  coldTintGreen = vec3(0.20, 0.70, 0.35);          // darker green outer
  
  // GRAY theme colour construction (Light Mode)
  vec3  warmTintGray  = vec3(0.92, 0.94, 0.93);          // lighter silver rim
  vec3  coldTintGray  = vec3(0.75, 0.78, 0.76);          // lighter slate outer

  vec3 warmTint = mix(warmTintGreen, warmTintGray, uTheme);
  vec3 coldTint = mix(coldTintGreen, coldTintGray, uTheme);

  vec3 glowColor = mix(warmTint, vColor, rimHeat);

  vec3 finalColor = mix(glowColor, glowColor * 1.35, vGlow * 0.4);

  // Ring adds bright flash
  vec3 ringGreen = vec3(0.80, 1.00, 0.85);
  vec3 ringGray  = vec3(0.95, 0.95, 0.95);
  finalColor += mix(ringGreen, ringGray, uTheme) * ring;

  float alpha = vAlpha * mask * clamp(glow, 0.0, 1.0);
  alpha = max(alpha, 0.0);

  // In Dark Mode (Additive), we output premultiplied color.
  // In Light Mode (Normal), we output raw color because Three.js NormalBlending will multiply by alpha.
  vec4 darkOutput  = vec4(finalColor * alpha, alpha);
  vec4 lightOutput = vec4(finalColor, alpha);

  gl_FragColor = mix(darkOutput, lightOutput, uTheme);
}
`;

export default fragmentShader;
