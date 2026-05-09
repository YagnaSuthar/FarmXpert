// FILE: components/animation/shaders/vertex.glsl
// ============================================================
// GPU Particle Vertex Shader — Production Grade
//
// Handles ALL per-particle movement on the GPU:
//   1. Shape morphing        (mix position → targetPosition)
//   2. Organic life motion   (layered sin/cos field noise)
//   3. Mouse magnetic force  (smooth distance falloff)
//   4. Hover energy wave     (radial explosion + ring pulse)
//   5. Depth breathing       (z oscillation for 3-D richness)
//   6. Dynamic point sizing  (depth-aware + hover scale)
// ============================================================

// ── Uniforms ─────────────────────────────────────────────────
uniform float uTime;        // elapsed seconds (continuous)
uniform float uProgress;    // morph t  [0 → 1]
uniform vec2  uMouse;       // normalised mouse [-1,1] per axis
uniform float uHover;       // hover blend [0 → 1]
uniform float uPixelRatio;  // device pixel ratio for size calc
uniform vec2  uResolution;  // viewport dimensions in px

// ── Per-particle attributes ───────────────────────────────────
attribute vec3  aInitialPosition;  // resting / source shape
attribute vec3  aTargetPosition;   // destination shape
attribute float aRandom;           // per-particle seed [0,1]
attribute float aScale;            // per-particle base size seed

// ── Varyings to fragment ──────────────────────────────────────
varying float vAlpha;        // final opacity for fragment
varying float vGlow;         // glow intensity for fragment
varying vec3  vColor;        // tinted colour for fragment

// ─────────────────────────────────────────────────────────────
// NOISE UTILITIES
// Compact, branchless pseudo-noise built from sin() —
// good enough for organic motion, zero texture lookups.
// ─────────────────────────────────────────────────────────────

// 1-D hash → pseudo-random float in [0,1]
float hash(float n) {
  return fract(sin(n) * 43758.5453123);
}

// 3-D → 1-D smooth noise (value noise, trilinear interp)
float noise3(vec3 p) {
  vec3 i = floor(p);
  vec3 f = fract(p);
  // Quintic smoothstep
  vec3 u = f * f * f * (f * (f * 6.0 - 15.0) + 10.0);

  float n000 = hash(i.x + 57.0 * i.y + 113.0 * i.z);
  float n100 = hash(i.x + 1.0 + 57.0 * i.y + 113.0 * i.z);
  float n010 = hash(i.x + 57.0 * (i.y + 1.0) + 113.0 * i.z);
  float n110 = hash(i.x + 1.0 + 57.0 * (i.y + 1.0) + 113.0 * i.z);
  float n001 = hash(i.x + 57.0 * i.y + 113.0 * (i.z + 1.0));
  float n101 = hash(i.x + 1.0 + 57.0 * i.y + 113.0 * (i.z + 1.0));
  float n011 = hash(i.x + 57.0 * (i.y + 1.0) + 113.0 * (i.z + 1.0));
  float n111 = hash(i.x + 1.0 + 57.0 * (i.y + 1.0) + 113.0 * (i.z + 1.0));

  return mix(
    mix(mix(n000, n100, u.x), mix(n010, n110, u.x), u.y),
    mix(mix(n001, n101, u.x), mix(n011, n111, u.x), u.y),
    u.z
  );
}

// Curl-like divergence-free offset built from noise gradient
// (avoids artificial clustering that plain noise creates)
vec3 curlOffset(vec3 p, float t) {
  float eps = 0.1;
  vec3 pT = p + vec3(t * 0.12);

  // Partial derivatives — approx gradient of 3 noise fields
  float nx0 = noise3(pT + vec3(eps, 0.0, 0.0));
  float nx1 = noise3(pT - vec3(eps, 0.0, 0.0));
  float ny0 = noise3(pT + vec3(0.0, eps, 0.0));
  float ny1 = noise3(pT - vec3(0.0, eps, 0.0));
  float nz0 = noise3(pT + vec3(0.0, 0.0, eps));
  float nz1 = noise3(pT - vec3(0.0, 0.0, eps));

  // Curl formula (cross of gradient)
  return vec3(
    (ny0 - ny1) - (nz0 - nz1),
    (nz0 - nz1) - (nx0 - nx1),
    (nx0 - nx1) - (ny0 - ny1)
  ) / (2.0 * eps);
}

// ─────────────────────────────────────────────────────────────
// MAIN
// ─────────────────────────────────────────────────────────────
void main() {

  // ── 0. Unique per-particle time offset ───────────────────────
  // Each particle lives in its own temporal phase so they never
  // all move in sync — critical for "alive" feeling.
  float seed     = aRandom;                       // [0,1]
  float phaseA   = seed * 6.2831853;              // [0, 2π]
  float phaseB   = hash(seed + 0.3) * 6.2831853;
  float slowTime = uTime * 0.35;                  // master slow clock
  float fastTime = uTime * 1.20;                  // for fine flicker

  // ── 1. BASE MORPH POSITION ───────────────────────────────────
  // Smoothstep the raw uProgress so the morph accelerates in
  // and decelerates out (ease-in-out), preventing the linear
  // "mechanical slide" look.
  float morphT   = smoothstep(0.0, 1.0, uProgress);
  vec3  morphPos = mix(aInitialPosition, aTargetPosition, morphT);

  // ── 2. ORGANIC LIFE MOTION ───────────────────────────────────
  // Layer 1 — low-frequency body drift (breathing feel)
  float driftAmp = 0.055 + seed * 0.025;
  vec3 drift = vec3(
    sin(slowTime * 0.7 + phaseA) * driftAmp,
    cos(slowTime * 0.5 + phaseB) * driftAmp,
    sin(slowTime * 0.9 + phaseA + 1.1) * driftAmp * 0.6
  );

  // Layer 2 — mid-frequency curl noise (swirling organic field)
  // Scale the position into noise space so different regions
  // of the shape move differently — prevents "block" motion.
  vec3 curlInput  = morphPos * 0.55 + vec3(seed * 7.3);
  vec3 curlMotion = curlOffset(curlInput, slowTime) * 0.07;

  // Layer 3 — high-frequency micro-jitter (shimmer)
  float shimmerAmp = 0.008;
  vec3 shimmer = vec3(
    sin(fastTime * 3.1 + phaseA * 2.3) * shimmerAmp,
    cos(fastTime * 2.7 + phaseB * 1.9) * shimmerAmp,
    sin(fastTime * 4.0 + phaseA)       * shimmerAmp * 0.5
  );

  vec3 livePos = morphPos + drift + curlMotion + shimmer;

  // ── 3. DEPTH BREATHING ───────────────────────────────────────
  // Adds gentle Z oscillation that makes the flat particle cloud
  // feel volumetric. Each particle breathes at its own rate.
  float breathe  = sin(slowTime * 0.4 + phaseA * 0.5) * 0.12;
  livePos.z     += breathe * (0.5 + seed * 0.5);

  // ── 4. MOUSE MAGNETIC FORCE ──────────────────────────────────
  // Project mouse from screen [-1,1] into approximate world space.
  // The particle cloud is centered at z=0, camera at z=5, FOV~60°.
  // tan(30°) ≈ 0.577 → at z=0 plane, world half-height ≈ 5*0.577
  float worldScale = 5.0 * 0.5773;
  vec3 mouseWorld  = vec3(
    uMouse.x * worldScale * (uResolution.x / uResolution.y),
    uMouse.y * worldScale,
    0.0
  );

  vec3  toMouse   = livePos - mouseWorld;
  float mouseDist = length(toMouse);

  // Magnetic force radius and strength
  float magnetRadius   = 1.4;
  float magnetStrength = 0.55;

  // Smooth repulsion falloff — zero outside radius, peaks at centre
  float magnetFalloff = 1.0 - smoothstep(0.0, magnetRadius, mouseDist);
  magnetFalloff       = magnetFalloff * magnetFalloff; // sharpen curve

  // Direction away from mouse (repel) — safe normalize
  vec3 repelDir = mouseDist > 0.001 ? (toMouse / mouseDist) : vec3(0.0, 1.0, 0.0);

  // Swirl tangent — perpendicular in XY plane for vortex feel
  vec3 swirlDir = vec3(-repelDir.y, repelDir.x, 0.0);
  float swirlMix = 0.28; // blend between pure repel and swirl

  vec3 mouseForce = mix(repelDir, swirlDir, swirlMix)
                    * magnetFalloff
                    * magnetStrength;

  livePos += mouseForce;

  // ── 5. HOVER EXPLOSION / ENERGY WAVE ─────────────────────────
  // On hover: particles radiate outward in a circular wave.
  // The wavefront travels from centre to edge using uTime so
  // it pulses continuously while hovered.
  if (uHover > 0.001) {

    // Radial direction from origin (safe for z=0 plane)
    vec3  radialDir  = normalize(vec3(livePos.x, livePos.y, livePos.z * 0.3));
    float radialDist = length(vec3(livePos.x, livePos.y, 0.0));

    // Pulsing wave ring — sin creates a travelling wavefront
    float wavePeriod = 1.8;  // seconds per cycle
    float waveWidth  = 0.6;  // ring thickness in world units
    float wavePhase  = mod(uTime * wavePeriod, 3.5);
    float waveMask   = exp(-pow((radialDist - wavePhase) / waveWidth, 2.0));

    // Base outward expansion (all particles push out)
    float expandForce = 0.55 + seed * 0.35;

    // Ring pulse on top of expansion
    float ringForce = waveMask * 1.1;

    vec3 hoverDisplace = radialDir * (expandForce + ringForce);

    // Spiral twist — add slight angular rotation to each ring
    float twistAngle = radialDist * 0.4 + uTime * 0.8;
    vec3  twist      = vec3(
      -sin(twistAngle) * radialDir.y,
       cos(twistAngle) * radialDir.x,
       sin(twistAngle + seed * 6.28) * 0.15
    );

    hoverDisplace += twist * waveMask * 0.3;

    livePos += hoverDisplace * uHover;
  }

  // ── 6. POINT SIZE ─────────────────────────────────────────────
  // Size varies by:
  //   • Per-particle seed (variety)
  //   • Depth (perspective feel — deeper = smaller)
  //   • Hover state (particles swell when energy wave hits)
  //   • Mouse proximity (particles near cursor grow slightly)

  float baseSize      = (1.4 + aScale * 2.2) * uPixelRatio;

  // Depth falloff — particles further in Z appear smaller
  float mvDepth       = (modelViewMatrix * vec4(livePos, 1.0)).z;
  float depthScale    = 1.0 / (1.0 - mvDepth * 0.04);

  // Hover size pulse
  float hoverPulse    = 1.0 + uHover * (0.8 + sin(uTime * 3.5 + seed * 6.28) * 0.4);

  // Mouse proximity bloom
  float proxBloom     = 1.0 + smoothstep(1.4, 0.0, length(
    vec2(livePos.x - mouseWorld.x, livePos.y - mouseWorld.y)
  )) * 0.9;

  gl_PointSize = baseSize * depthScale * hoverPulse * proxBloom;

  // ── 7. FINAL CLIP POSITION ────────────────────────────────────
  gl_Position = projectionMatrix * modelViewMatrix * vec4(livePos, 1.0);

  // ── 8. VARYINGS ───────────────────────────────────────────────
  // Alpha: fade by depth and slightly randomise so the cloud
  // has transparent wisps at the edges.
  float depthAlpha = clamp(1.0 + mvDepth * 0.06, 0.3, 1.0);
  float seedAlpha  = 0.55 + seed * 0.45;
  vAlpha = depthAlpha * seedAlpha;

  // Glow: brighter near mouse, brighter during hover wave
  float mouseGlow  = smoothstep(magnetRadius, 0.0, mouseDist) * 0.7;
  float hoverGlow  = uHover * (0.5 + sin(uTime * 4.0 + seed * 6.28) * 0.3);
  vGlow = clamp(mouseGlow + hoverGlow, 0.0, 1.0);

  // Colour: base teal-blue shifted toward white on glow
  // The fragment shader will use this as the base tint.
  float colorShift = vGlow * 0.55 + uHover * 0.2;
  vColor = mix(
    vec3(0.38, 0.72, 1.00),   // cool particle blue
    vec3(1.00, 1.00, 1.00),   // white-hot centre
    colorShift
  );
}
