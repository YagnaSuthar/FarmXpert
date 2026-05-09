// ============================================================
// FILE: components/animation/ParticleSystem.js
//
// Merged production particle engine.
// Combines the original CPU scaffold API with the new fully
// GPU-driven ShaderMaterial architecture.
//
// What is preserved from the original file
// ─────────────────────────────────────────
//   ✓  seededRandom()         — deterministic LCG PRNG
//   ✓  randomInsideSphere()   — rejection-sampled uniform scatter
//   ✓  CONFIG structure       — single source of truth for tuning
//   ✓  scatter()              — randomise to sphere cloud
//   ✓  converge()             — gather toward a focal point
//   ✓  setTargetAt()          — per-particle target override
//   ✓  getPositionAt()        — read current world-space position
//   ✓  dispose()              — full GPU + heap teardown
//   ✓  mesh.frustumCulled     — always false (particles span screen)
//
// What is upgraded / replaced
// ───────────────────────────
//   ✗  PointsMaterial         → ShaderMaterial (vertex + fragment GLSL)
//   ✗  applyLerp() JS loop    → mix() in vertex shader via uProgress
//   ✗  applyDrift() JS loop   → curl-noise field in vertex shader
//   ✗  position.needsUpdate   → uniforms only; attributes are static
//   ✗  _velocity buffer       → GPU-side drift, no JS accumulation
//
// New additions
// ─────────────
//   +  morphTo(shapeKey)      — GPU morph between named shapes
//   +  tick(elapsed, delta)   — updates uniforms only (zero JS loops)
//   +  resize(w, h)           — keeps uResolution / uPixelRatio sync'd
//   +  mouse / hover events   — magnetic force + energy wave in GLSL
//   +  createMorphSequence()  — auto-cycling morph timeline helper
// ============================================================

import * as THREE from 'three';
import { generateSphere } from './shapes/generateSphere.js';
import { generateMapPin  } from './shapes/generateMapPin.js';
import { generateLeaf    } from './shapes/generateLeaf.js';

import vertexShader   from './shaders/vertexShader.js';
import fragmentShader from './shaders/fragmentShader.js';

// ─────────────────────────────────────────────────────────────
// CONFIG — single source of truth
// Merges original keys with new GPU-side tuning knobs.
// ─────────────────────────────────────────────────────────────
const CONFIG = {
  // ── Particle count ──────────────────────────────────────────
  count:        10_000,

  // ── Spawn / scatter volume (world units) ────────────────────
  // Preserved from original (was spawnRadius: 6.0)
  spawnRadius:  6.0,

  // ── GPU morph lerp speed ─────────────────────────────────────
  // Conceptually replaces original lerpSpeed.position (0.045).
  // Drives uProgress lerp per frame × frameFactor.
  morphSpeed:   0.042,

  // ── Hover transition speed ───────────────────────────────────
  hoverSpeed:   0.08,

  // ── Mouse smooth lerp factor ─────────────────────────────────
  // Lower = more lag = silkier feel.
  mouseLerp:    0.065,

  // ── Pixel ratio cap (HiDPI performance guard) ────────────────
  pixelRatioCap: 2,
};

// ── Shape catalogue ──────────────────────────────────────────
// Keys are the public API surface: system.morphTo('mapPin') etc.
const SHAPES = {
  sphere : (n) => generateSphere (n, 2.0, 0.0),
  mapPin : (n) => generateMapPin (n, 2.0, 0.08),
  leaf   : (n) => generateLeaf   (n, 2.0, 0.06),
};

// ─────────────────────────────────────────────────────────────
// INTERNAL HELPERS
// Preserved verbatim from original — still needed for
// scatter() and converge() which generate CPU-side positions
// once per API call (not per frame).
// ─────────────────────────────────────────────────────────────

/**
 * seededRandom — lightweight LCG PRNG (original, unchanged).
 * Deterministic across hot-reloads and SSR hydration.
 *
 * @param   {number}       seed
 * @returns {() => number} closure returning floats in [0, 1)
 */
function seededRandom(seed = 42) {
  let s = seed;
  return () => {
    s = (s * 1664525 + 1013904223) & 0xffffffff;
    return (s >>> 0) / 0xffffffff;
  };
}

/**
 * randomInsideSphere — uniform point inside a sphere (original, unchanged).
 * Rejection sampling avoids polar-coordinate clustering at centre.
 *
 * @param   {() => number}               rand
 * @param   {number}                     radius
 * @returns {{ x: number, y: number, z: number }}
 */
function randomInsideSphere(rand, radius) {
  let x, y, z, d;
  do {
    x = (rand() * 2 - 1) * radius;
    y = (rand() * 2 - 1) * radius;
    z = (rand() * 2 - 1) * radius;
    d = x * x + y * y + z * z;
  } while (d > radius * radius);
  return { x, y, z };
}

// ─────────────────────────────────────────────────────────────
// GEOMETRY BUILDER
//
// Original: exposed only 'position' with DynamicDrawUsage,
//           re-uploaded every frame from CPU lerp results.
//
// New:      exposes four attributes, all StaticDrawUsage.
//           Only aInitialPosition + aTargetPosition are ever
//           mutated — and only on a morph/scatter/converge call,
//           NOT every frame.  The GPU reads them via mix().
// ─────────────────────────────────────────────────────────────

/**
 * buildGeometry
 *
 * @param   {Float32Array}       initialPositions — flat XYZ source shape
 * @param   {number}             count
 * @returns {THREE.BufferGeometry}
 */
function buildGeometry(initialPositions, count) {
  const geometry = new THREE.BufferGeometry();

  // Source shape — where particles depart from.
  geometry.setAttribute(
    'aInitialPosition',
    new THREE.BufferAttribute(initialPositions.slice(), 3),
  );

  // Destination shape — where particles morph toward.
  // Starts identical to source; morphTo/scatter/converge write here.
  geometry.setAttribute(
    'aTargetPosition',
    new THREE.BufferAttribute(initialPositions.slice(), 3),
  );

  // Per-particle random seed [0,1] — drives all noise phase offsets
  // in vertex shader so no two particles ever move identically.
  const randoms = new Float32Array(count);
  for (let i = 0; i < count; i++) randoms[i] = Math.random();
  geometry.setAttribute(
    'aRandom',
    new THREE.BufferAttribute(randoms, 1),
  );

  // Per-particle size seed [0,1] — drives point-size variety.
  const scales = new Float32Array(count);
  for (let i = 0; i < count; i++) scales[i] = Math.random();
  geometry.setAttribute(
    'aScale',
    new THREE.BufferAttribute(scales, 1),
  );

  geometry.setDrawRange(0, count);

  return geometry;
}

// ─────────────────────────────────────────────────────────────
// MATERIAL BUILDER
//
// Original: THREE.PointsMaterial (placeholder)
// New:      THREE.ShaderMaterial with custom vertex + fragment
//
// AdditiveBlending + depthWrite:false preserved from original.
// ─────────────────────────────────────────────────────────────

/**
 * buildMaterial
 *
 * @param   {THREE.Vector2}      resolution — shared ref; resize updates it
 * @returns {THREE.ShaderMaterial}
 */
function buildMaterial(resolution) {
  return new THREE.ShaderMaterial({
    vertexShader,
    fragmentShader,

    uniforms: {
      uTime       : { value: 0.0 },
      uProgress   : { value: 0.0 },   // morph t  [0 → 1]
      uMouse      : { value: new THREE.Vector2(0, 0) },
      uHover      : { value: 0.0 },   // hover blend [0 → 1]
      uPixelRatio : { value: Math.min(window.devicePixelRatio, CONFIG.pixelRatioCap) },
      uResolution : { value: resolution },
      uOffset     : { value: new THREE.Vector3(0, 0, 0) },  // scroll-driven offset
      uTheme      : { value: 0.0 },   // 0.0 for dark, 1.0 for light
    },

    blending    : THREE.AdditiveBlending, // preserved from original
    depthWrite  : false,                  // preserved from original
    depthTest   : true,
    transparent : true,
    vertexColors: false,
  });
}

// ─────────────────────────────────────────────────────────────
// ParticleSystem class
// ─────────────────────────────────────────────────────────────

export class ParticleSystem {
  /**
   * Constructor signature is extended from the original:
   *   Original → new ParticleSystem(options?)
   *   New      → new ParticleSystem(scene, renderer, options?)
   *
   * The scene and renderer are now required because the system
   * needs to self-register to the scene and attach DOM events.
   *
   * @param {THREE.Scene}         scene
   * @param {THREE.WebGLRenderer} renderer
   * @param {object}              [options] — partial CONFIG overrides
   */
  constructor(scene, renderer, options = {}) {
    // ── Merge config (same pattern as original) ──────────────
    this._config = { ...CONFIG, ...options };
    this._count  = this._config.count;

    this._scene    = scene;
    this._renderer = renderer;

    // ── Resolution uniform (shared Vector2 ref) ───────────────
    // resize() updates this in-place — the uniform sees the new
    // value immediately without a fresh uniform.value assignment.
    this._resolution = new THREE.Vector2(
      renderer.domElement.clientWidth  * Math.min(window.devicePixelRatio, CONFIG.pixelRatioCap),
      renderer.domElement.clientHeight * Math.min(window.devicePixelRatio, CONFIG.pixelRatioCap),
    );

    // ── Internal animation state ──────────────────────────────
    this._morphProgress   = 0.0;
    this._morphTarget     = 0.0;
    this._hoverValue      = 0.0;
    this._hoverTarget     = 0.0;
    this._mouseSmooth     = new THREE.Vector2(0, 0);
    this._mouseRaw        = new THREE.Vector2(0, 0);
    this._currentShapeKey = 'sphere';
    this._disposed        = false;
    this._offsetTarget    = new THREE.Vector3(0, 0, 0);
    this._offsetCurrent   = new THREE.Vector3(0, 0, 0);

    // ── Allocate initial shape data ───────────────────────────
    // Original used seededRandom + randomInsideSphere.
    // New uses the shape generator — sphere is the default.
    const initialPositions = SHAPES.sphere(this._count);

    // ── Build Three.js objects ────────────────────────────────
    /** @type {THREE.BufferGeometry} */
    this.geometry = buildGeometry(initialPositions, this._count);

    /** @type {THREE.ShaderMaterial} (was PointsMaterial in original) */
    this.material = buildMaterial(this._resolution);

    /**
     * @type {THREE.Points}
     * Still named `this.mesh` for drop-in compatibility with any
     * code that was doing `scene.add(system.mesh)`.
     */
    this.mesh = new THREE.Points(this.geometry, this.material);
    this.mesh.frustumCulled = false; // preserved from original

    scene.add(this.mesh);

    // ── Bind + attach DOM event listeners ─────────────────────
    this._onMouseMove  = this._handleMouseMove.bind(this);
    this._onMouseEnter = this._handleMouseEnter.bind(this);
    this._onMouseLeave = this._handleMouseLeave.bind(this);
    this._onTouchMove  = this._handleTouchMove.bind(this);

    // Attach mouse move globally to window so it tracks even if canvas has pointer-events: none
    window.addEventListener('mousemove',  this._onMouseMove);
    window.addEventListener('touchmove',  this._onTouchMove, { passive: true });
    
    // Hover events can stay on canvas or we just leave them globally disabled
    // since the magnetic mouse repulsion works globally.
    const canvas = renderer.domElement;
    canvas.addEventListener('mouseenter', this._onMouseEnter);
    canvas.addEventListener('mouseleave', this._onMouseLeave);
  }

  // ── Public API ────────────────────────────────────────────

  /**
   * setTheme — update the theme uniform (0.0 = dark, 1.0 = light).
   * @param {boolean} isLight
   */
  setTheme(isLight) {
    if (this._disposed) return;
    this.material.uniforms.uTheme.value = isLight ? 1.0 : 0.0;
    this.material.blending = isLight ? THREE.NormalBlending : THREE.AdditiveBlending;
    this.material.needsUpdate = true;
  }

  /**
   * tick — advance particle simulation by one frame.
   *
   * Original: ran applyDrift() + applyLerp() JS loops (CPU-bound).
   * New:      updates GPU uniforms only — zero per-particle JS.
   *           All motion (drift, morph, mouse, hover) lives in GLSL.
   *
   * Signature is backward-compatible: (delta, elapsed) unchanged.
   *
   * @param {number} elapsed — total seconds since start  → uTime
   * @param {number} delta   — seconds since last frame   → frame scaling
   */
  tick(elapsed, delta) {
    if (this._disposed) return;

    const U = this.material.uniforms;

    // ── Continuous time → drives all shader animation ────────
    U.uTime.value = elapsed;

    // ── Frame-rate-independent scale ─────────────────────────
    // Clamp to 3 protects against huge delta on tab restore.
    // Original had the same guard concept in its lerp logic.
    const frameFactor = Math.min(delta * 60, 3.0);

    // ── Morph progress ────────────────────────────────────────
    // Replaces applyLerp() — drives mix() in vertex.glsl.
    // morphSpeed (0.042) ≈ original lerpSpeed.position (0.045).
    this._morphProgress +=
      (this._morphTarget - this._morphProgress) *
      this._config.morphSpeed * frameFactor;
    U.uProgress.value = this._morphProgress;

    // ── Hover blend ───────────────────────────────────────────
    this._hoverValue +=
      (this._hoverTarget - this._hoverValue) *
      this._config.hoverSpeed * frameFactor;
    U.uHover.value = this._hoverValue;

    // ── Mouse smooth lerp ─────────────────────────────────────
    this._mouseSmooth.lerp(this._mouseRaw, this._config.mouseLerp * frameFactor);
    U.uMouse.value.copy(this._mouseSmooth);

    // ── Offset smooth lerp (scroll-driven position) ────────────
    this._offsetCurrent.lerp(this._offsetTarget, 0.04 * frameFactor);
    U.uOffset.value.copy(this._offsetCurrent);

    // NOTE: geometry attributes are NOT marked needsUpdate here.
    // They're only dirty after morphTo / scatter / converge writes.
    // This is the key perf difference from the original design.
  }

  /**
   * setHoverTarget — externally control the hover state (uHover target).
   * Useful when you want UI interactions to drive particle energy.
   *
   * @param {number} value - expected range [0,1]
   */
  setHoverTarget(value) {
    if (this._disposed) return;
    const v = Number.isFinite(value) ? value : 0;
    this._hoverTarget = Math.max(0, Math.min(1, v));
  }

  /**
   * setOffset — smoothly move the entire particle system in world space.
   * Used for scroll-driven repositioning (hero → agents section).
   *
   * @param {number} x
   * @param {number} y
   * @param {number} z
   */
  setOffset(x, y, z) {
    if (this._disposed) return;
    this._offsetTarget.set(x, y, z);
  }

  /**
   * setOffsetImmediate — jump to position without lerp.
   */
  setOffsetImmediate(x, y, z) {
    if (this._disposed) return;
    this._offsetTarget.set(x, y, z);
    this._offsetCurrent.set(x, y, z);
    if (this.material?.uniforms?.uOffset) {
      this.material.uniforms.uOffset.value.set(x, y, z);
    }
  }

  /**
   * setHoverImmediate — sets both current hover value and target.
   * Use sparingly; typically only for initial sync.
   *
   * @param {number} value - expected range [0,1]
   */
  setHoverImmediate(value) {
    if (this._disposed) return;
    const v = Number.isFinite(value) ? value : 0;
    const clamped = Math.max(0, Math.min(1, v));
    this._hoverTarget = clamped;
    this._hoverValue = clamped;
    if (this.material?.uniforms?.uHover) this.material.uniforms.uHover.value = clamped;
  }

  /**
   * morphTo — smooth GPU transition to a named shape (time-based).
   */
  morphTo(shapeKey) {
    if (this._disposed) return;
    if (!SHAPES[shapeKey]) {
      console.warn(`[ParticleSystem] Unknown shape key: "${shapeKey}"`);
      return;
    }
    if (shapeKey === this._currentShapeKey) return;

    const initialAttr = this.geometry.getAttribute('aInitialPosition');
    const targetAttr  = this.geometry.getAttribute('aTargetPosition');

    // 1. Freeze current target as new departure point
    initialAttr.array.set(targetAttr.array);
    initialAttr.needsUpdate = true;

    // 2. Write destination shape
    targetAttr.array.set(SHAPES[shapeKey](this._count));
    targetAttr.needsUpdate = true;

    // 3. Reset shader progress → animates 0 → 1
    this.material.uniforms.uProgress.value = 0.0;
    this._morphProgress   = 0.0;
    this._morphTarget     = 1.0;
    this._currentShapeKey = shapeKey;
  }

  /**
   * setMorphShapes — manually set initial and target shapes without starting a time-based transition.
   * Useful for scroll-driven animations where progress is controlled externally.
   *
   * @param {string} initialKey
   * @param {string} targetKey
   */
  setMorphShapes(initialKey, targetKey) {
    if (this._disposed) return;
    if (!SHAPES[initialKey] || !SHAPES[targetKey]) return;

    const initialAttr = this.geometry.getAttribute('aInitialPosition');
    const targetAttr  = this.geometry.getAttribute('aTargetPosition');

    initialAttr.array.set(SHAPES[initialKey](this._count));
    initialAttr.needsUpdate = true;

    targetAttr.array.set(SHAPES[targetKey](this._count));
    targetAttr.needsUpdate = true;

    this._currentShapeKey = targetKey; // Logically we are targeting this
  }

  /**
   * setMorphProgress — manually drive the morph transition.
   * Skips the internal time-based lerp.
   *
   * @param {number} progress (0.0 to 1.0)
   */
  setMorphProgress(progress) {
    if (this._disposed) return;
    const clamped = Math.max(0, Math.min(1, progress));
    this.material.uniforms.uProgress.value = clamped;
    this._morphProgress = clamped;
    this._morphTarget = clamped; // Prevent tick() from overriding it
  }

  /**
   * scatter — randomise all targets to a sphere cloud.
   * Preserved from original — now triggers a GPU morph instead of
   * mutating the CPU position buffer directly.
   *
   * @param {number} [radius] — override spawn radius
   */
  scatter(radius = this._config.spawnRadius) {
    if (this._disposed) return;

    const initialAttr = this.geometry.getAttribute('aInitialPosition');
    const targetAttr  = this.geometry.getAttribute('aTargetPosition');

    // Preserve departure-from-current (same as morphTo)
    initialAttr.array.set(targetAttr.array);
    initialAttr.needsUpdate = true;

    // Different seed each call — original behaviour preserved exactly
    const rand = seededRandom(Date.now() & 0xffff);
    for (let i = 0; i < this._count; i++) {
      const { x, y, z } = randomInsideSphere(rand, radius);
      const i3 = i * 3;
      targetAttr.array[i3 + 0] = x;
      targetAttr.array[i3 + 1] = y;
      targetAttr.array[i3 + 2] = z;
    }
    targetAttr.needsUpdate = true;

    this.material.uniforms.uProgress.value = 0.0;
    this._morphProgress   = 0.0;
    this._morphTarget     = 1.0;
    this._currentShapeKey = '__scatter__';
  }

  /**
   * converge — drive all targets toward a single focal point.
   * Preserved from original — updated to trigger GPU morph.
   *
   * @param {THREE.Vector3} [point]  — world-space target (default: origin)
   * @param {number}        [jitter] — random radius around point
   */
  converge(point = new THREE.Vector3(0, 0, 0), jitter = 0.05) {
    if (this._disposed) return;

    const initialAttr = this.geometry.getAttribute('aInitialPosition');
    const targetAttr  = this.geometry.getAttribute('aTargetPosition');

    initialAttr.array.set(targetAttr.array);
    initialAttr.needsUpdate = true;

    const rand = seededRandom(7); // fixed seed → reproducible cluster
    for (let i = 0; i < this._count; i++) {
      const i3 = i * 3;
      targetAttr.array[i3 + 0] = point.x + (rand() - 0.5) * jitter * 2;
      targetAttr.array[i3 + 1] = point.y + (rand() - 0.5) * jitter * 2;
      targetAttr.array[i3 + 2] = point.z + (rand() - 0.5) * jitter * 2;
    }
    targetAttr.needsUpdate = true;

    this.material.uniforms.uProgress.value = 0.0;
    this._morphProgress   = 0.0;
    this._morphTarget     = 1.0;
    this._currentShapeKey = '__converge__';
  }

  /**
   * setTargetAt — override the target of a single particle by index.
   * Preserved from original — now writes aTargetPosition.
   * Call resetMorph() after a bulk batch to trigger GPU interpolation.
   *
   * @param {number} index
   * @param {number} x
   * @param {number} y
   * @param {number} z
   */
  setTargetAt(index, x, y, z) {
    if (this._disposed || index < 0 || index >= this._count) return;
    const attr = this.geometry.getAttribute('aTargetPosition');
    const i3   = index * 3;
    attr.array[i3 + 0] = x;
    attr.array[i3 + 1] = y;
    attr.array[i3 + 2] = z;
    attr.needsUpdate   = true;
  }

  /**
   * resetMorph — re-trigger GPU interpolation after manual setTargetAt
   * bulk writes. Freezes current target as new initial then animates.
   */
  resetMorph() {
    const initialAttr = this.geometry.getAttribute('aInitialPosition');
    const targetAttr  = this.geometry.getAttribute('aTargetPosition');
    initialAttr.array.set(targetAttr.array);
    initialAttr.needsUpdate = true;

    this.material.uniforms.uProgress.value = 0.0;
    this._morphProgress = 0.0;
    this._morphTarget   = 1.0;
  }

  /**
   * getPositionAt — read world-space position of particle i.
   * Original returned the CPU position buffer (which no longer
   * exists). New version reads aTargetPosition — the authoritative
   * resting position from the JS side.
   * Returns a new THREE.Vector3 (avoid in hot loops).
   *
   * @param   {number}        index
   * @returns {THREE.Vector3}
   */
  getPositionAt(index) {
    const attr = this.geometry.getAttribute('aTargetPosition');
    const i3   = index * 3;
    return new THREE.Vector3(
      attr.array[i3 + 0],
      attr.array[i3 + 1],
      attr.array[i3 + 2],
    );
  }

  /**
   * resize — sync uResolution + uPixelRatio with new canvas dimensions.
   * Call from ParticleCanvas ResizeObserver.
   *
   * @param {number} width
   * @param {number} height
   */
  resize(width, height) {
    const dpr = Math.min(window.devicePixelRatio, CONFIG.pixelRatioCap);
    this._resolution.set(width * dpr, height * dpr);
    this.material.uniforms.uPixelRatio.value = dpr;
  }

  // ── Read-only state getters (original .count preserved) ─────

  /** Total number of simulated particles. */
  get count() { return this._count; }

  /** Current shape key ('sphere' | 'mapPin' | 'leaf' | '__scatter__' …) */
  get currentShape() { return this._currentShapeKey; }

  /** True while a morph transition is still in progress. */
  get isMorphing() {
    return Math.abs(this._morphTarget - this._morphProgress) > 0.001;
  }

  // ── Disposal ─────────────────────────────────────────────────

  /**
   * dispose — full GPU + JS heap teardown.
   * Extended from original: also removes DOM event listeners and
   * removes the mesh from the scene.
   */
  dispose() {
    if (this._disposed) return;
    this._disposed = true;

    // Remove DOM listeners
    window.removeEventListener('mousemove',  this._onMouseMove);
    window.removeEventListener('touchmove',  this._onTouchMove);

    const canvas = this._renderer.domElement;
    canvas.removeEventListener('mouseenter', this._onMouseEnter);
    canvas.removeEventListener('mouseleave', this._onMouseLeave);

    // Remove from scene
    this._scene.remove(this.mesh);

    // Free GPU memory (same pattern as original)
    this.geometry.dispose();
    this.material.dispose();

    // Null large refs so GC can reclaim immediately (same as original)
    this.geometry  = null;
    this.material  = null;
    this.mesh      = null;
    this._scene    = null;
    this._renderer = null;
  }

  // ── Private — DOM event handlers ─────────────────────────────

  /**
   * Normalise clientX/Y to NDC [-1, 1] relative to the canvas rect.
   * Works correctly even when the canvas does not fill the viewport.
   */
  _normaliseMouse(clientX, clientY) {
    const rect = this._renderer.domElement.getBoundingClientRect();
    return new THREE.Vector2(
       ((clientX - rect.left) / rect.width)  * 2 - 1,
      -((clientY - rect.top)  / rect.height) * 2 + 1,
    );
  }

  _handleMouseMove(e) {
    this._mouseRaw.copy(this._normaliseMouse(e.clientX, e.clientY));
  }

  _handleMouseEnter() {
    this._hoverTarget = 1.0;
  }

  _handleMouseLeave() {
    this._hoverTarget = 0.0;
    this._mouseRaw.set(0, 0); // let magnetic force dissipate off-screen
  }

  _handleTouchMove(e) {
    const touch = e.touches[0];
    if (!touch) return;
    this._mouseRaw.copy(this._normaliseMouse(touch.clientX, touch.clientY));
    this._hoverTarget = 1.0;
  }
}

// ─────────────────────────────────────────────────────────────
// createMorphSequence — auto-cycling morph timeline helper
//
// Usage:
//   const seq = createMorphSequence(system, ['sphere','mapPin','leaf'], 3200)
//   seq.start()
//   seq.jumpTo('leaf')
//   seq.stop()
// ─────────────────────────────────────────────────────────────

export function createMorphSequence(
  system,
  sequence   = ['sphere', 'mapPin', 'leaf'],
  intervalMs = 3200,
) {
  let index   = 0;
  let timerId = null;
  let running = false;

  const advance = () => {
    index = (index + 1) % sequence.length;
    system.morphTo(sequence[index]);
  };

  return {
    start() {
      if (running) return;
      running = true;
      timerId = setInterval(advance, intervalMs);
    },
    stop() {
      running = false;
      if (timerId !== null) {
        clearInterval(timerId);
        timerId = null;
      }
    },
    jumpTo(shapeKey) {
      system.morphTo(shapeKey);
      const idx = sequence.indexOf(shapeKey);
      if (idx !== -1) index = idx;
    },
    get currentIndex() { return index; },
    get isRunning()    { return running; },
  };
}

// ─────────────────────────────────────────────────────────────
// Named exports only — matches original export style.
// Import as:
//   import { ParticleSystem, createMorphSequence } from './ParticleSystem'
// ─────────────────────────────────────────────────────────────