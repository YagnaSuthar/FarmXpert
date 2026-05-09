// FILE: components/animation/shaders/fragment.glsl
// ============================================================
// GPU Particle Fragment Shader — Production Grade
//
// Runs once per pixel INSIDE each gl_PointSize square.
// Responsible for:
//   1. Circular mask   — discard corners of point quad
//   2. Soft glow core  — multi-layer radial falloff
//   3. Energy ring     — thin bright rim on hover
//   4. Chromatic tint  — colour shift from varyings
//   5. Premultiplied α — correct for additive blend mode
// ============================================================

precision highp float;

// ── Uniforms ─────────────────────────────────────────────────
uniform float uTime;    // for animated ring shimmer
uniform float uHover;   // hover blend [0 → 1]

// ── Varyings from vertex ──────────────────────────────────────
varying float vAlpha;   // per-particle opacity
varying float vGlow;    // per-particle glow intensity
varying vec3  vColor;   // per-particle tint

// ─────────────────────────────────────────────────────────────
// RADIAL HELPERS
// ─────────────────────────────────────────────────────────────

// Signed distance from centre of point quad.
// gl_PointCoord ∈ [0,1] per axis → centre is (0.5, 0.5)
float pointDist() {
  return length(gl_PointCoord - 0.5);
}

// Smooth circular mask: 1 at centre, 0 at edge (radius 0.5)
float circleMask(float d, float softness) {
  return 1.0 - smoothstep(0.5 - softness, 0.5, d);
}

// ─────────────────────────────────────────────────────────────
// GLOW LAYERS
// Each layer is a radial intensity that falls off differently.
// Summing layers of different widths creates the HDR "bloom"
// look without a post-process pass.
// ─────────────────────────────────────────────────────────────

// Layer 1 — tight core  (very bright centre pinpoint)
float glowCore(float d) {
  return exp(-d * 28.0);
}

// Layer 2 — mid halo  (primary glow body)
float glowMid(float d) {
  return exp(-d * 10.0) * 0.55;
}

// Layer 3 — outer corona  (large soft bloom)
float glowOuter(float d) {
  return exp(-d * 4.5) * 0.22;
}

// ─────────────────────────────────────────────────────────────
// ENERGY RING
// A thin bright annulus that pulses outward on hover.
// Built from a narrow Gaussian centred at a moving radius.
// ─────────────────────────────────────────────────────────────
float energyRing(float d, float time, float hover) {
  // Ring radius oscillates between 0.15 and 0.42
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

  // ── 1. Hard discard outside circle boundary ───────────────
  // Eliminates the square corners of the point sprite quad.
  // Using 0.5 as the clip radius means each particle is a
  // perfect circle filling the full point-size square.
  if (d > 0.5) discard;

  // ── 2. Soft circular mask ─────────────────────────────────
  // 0.06 softness gives a gentle anti-aliased edge.
  float mask = circleMask(d, 0.06);

  // ── 3. Multi-layer glow composition ──────────────────────
  // Layers are additive — they can exceed 1.0 intentionally.
  // This creates the HDR hot-spot look without actual HDR.
  float glow =
      glowCore(d)    * (1.0 + vGlow * 1.8)  // core brightens on hover/mouse
    + glowMid(d)     * (0.9 + vGlow * 0.7)
    + glowOuter(d)   * (0.7 + vGlow * 0.4);

  // ── 4. Energy ring overlay ────────────────────────────────
  float ring = energyRing(d, uTime, uHover);
  glow += ring;

  // ── 5. Colour construction ────────────────────────────────
  // vColor is the base particle tint (blue→white gradient
  // computed in the vertex shader).
  // We further tint the outer halo slightly warmer to mimic
  // the spectral dispersion of physical glow.
  float rimHeat  = 1.0 - smoothstep(0.1, 0.4, d); // 1 at centre, 0 at rim
  vec3  warmTint = vec3(0.95, 0.80, 1.00);          // lavender-warm rim
  vec3  coldTint = vec3(0.40, 0.75, 1.00);          // cyan-cold outer

  vec3 glowColor = mix(warmTint, vColor, rimHeat);

  // Boost colour saturation on hover (vGlow encodes this)
  vec3 finalColor = mix(glowColor, glowColor * 1.35, vGlow * 0.4);

  // Ring adds near-white flash
  finalColor += vec3(1.0, 0.96, 0.88) * ring;

  // ── 6. Opacity ────────────────────────────────────────────
  // Combine:
  //   • vAlpha    — per-particle base opacity from vertex
  //   • mask      — circular soft boundary
  //   • glow      — HDR brightness (can push alpha > 1 for additive blend)
  // The THREE.js material uses AdditiveBlending so colours add
  // up on the GPU compositing stage — we want alpha to stay
  // proportional to glow intensity, not binary on/off.
  float alpha = vAlpha * mask * clamp(glow, 0.0, 1.0);

  // Minimum alpha so even background particles are faintly visible
  alpha = max(alpha, 0.0);

  // ── 7. Premultiplied alpha ────────────────────────────────
  // With AdditiveBlending, Three.js expects un-premultiplied
  // colour × alpha in gl_FragColor. The blending equation adds
  // srcColor × srcAlpha to the framebuffer, which gives the
  // correct bright-on-dark additive glow.
  gl_FragColor = vec4(finalColor * alpha, alpha);
}
