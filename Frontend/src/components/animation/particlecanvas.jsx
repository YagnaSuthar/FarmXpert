// FILE: components/animation/ParticleCanvas.jsx
// ============================================================
// Three.js rendering layer — updated to wire ParticleSystem.
//
// Changes from stub version:
//   • Instantiates ParticleSystem after scene/renderer boot
//   • Passes elapsed + delta to system.tick() each frame
//   • Passes resize dims to system.resize()
//   • Exposes systemRef so parent components can call morphTo()
//   • Full cleanup on unmount via system.dispose()
// ============================================================

'use client';

import { useRef, useEffect, useCallback } from 'react';
import * as THREE from 'three';
import { ParticleSystem, createMorphSequence } from './particlesystem.js';
import { useTheme } from '@/components/layout/ThemeProvider';

// ── Constants ─────────────────────────────────────────────────
const CAMERA_FOV      = 60;
const CAMERA_NEAR     = 0.1;
const CAMERA_FAR      = 1000;
const CAMERA_Z        = 5;
const PIXEL_RATIO_CAP = 2;

// ── Factories (same as before) ────────────────────────────────
function createScene() {
  return new THREE.Scene();
}

function createCamera(width, height) {
  const camera = new THREE.PerspectiveCamera(
    CAMERA_FOV, width / height, CAMERA_NEAR, CAMERA_FAR,
  );
  camera.position.set(0, 0, CAMERA_Z);
  camera.lookAt(0, 0, 0);
  return camera;
}

function createRenderer(canvas, width, height) {
  const renderer = new THREE.WebGLRenderer({
    canvas,
    alpha           : true,
    antialias       : true,
    powerPreference : 'high-performance',
  });
  renderer.setSize(width, height, false);
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, PIXEL_RATIO_CAP));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.setClearColor(0x000000, 0); // transparent clear
  return renderer;
}

// ─────────────────────────────────────────────────────────────
// ParticleCanvas
// ─────────────────────────────────────────────────────────────

/**
 * @param {object}   props
 * @param {React.Ref} [props.systemRef]  — forwarded ref to access
 *   the ParticleSystem instance externally (for morphTo calls).
 * @param {boolean}  [props.autoMorph]  — if true, starts the
 *   built-in morph sequence automatically (default: true).
 * @param {number}   [props.morphInterval] — ms between auto morphs
 */
export default function ParticleCanvas({
  systemRef,
  autoMorph    = true,
  morphInterval = 3200,
  className = '',
}) {
  const canvasRef  = useRef(null);
  const _systemRef = useRef(null); // internal ref always populated
  const { theme }  = useTheme();

  // ── Sync Theme ───────────────────────────────────────────
  useEffect(() => {
    if (_systemRef.current) {
      _systemRef.current.setTheme(theme === 'light');
    }
  }, [theme]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const parent = canvas.parentElement;
    if (!parent) return;

    // Force layout calc to ensure parent has dimensions
    const rect = parent.getBoundingClientRect();
    const w = Math.max(1, Math.floor(rect.width));
    const h = Math.max(1, Math.floor(rect.height));

    console.log('[ParticleCanvas] Init size:', w, 'x', h);

    console.log('[ParticleCanvas] Canvas parent:', parent?.className, 'Canvas in DOM:', document.contains(canvas));

    // ── Bootstrap Three.js ──────────────────────────────────
    const scene    = createScene();
    const camera   = createCamera(w, h);
    const renderer = createRenderer(canvas, w, h);
    const clock    = new THREE.Clock();

    // ── Instantiate particle system ─────────────────────────
    let system;
    try {
      system = new ParticleSystem(scene, renderer);
      console.log('[ParticleCanvas] ParticleSystem created:', system.mesh.geometry.attributes);
    } catch (err) {
      console.error('[ParticleCanvas] Failed to create ParticleSystem:', err);
      return;
    }
    _systemRef.current = system;
    if (systemRef) systemRef.current = system;

    // Set initial theme
    system.setTheme(theme === 'light');

    // ── Optional auto-morph sequence ────────────────────────
    let sequence = null;
    if (autoMorph) {
      sequence = createMorphSequence(
        system,
        ['sphere', 'mapPin', 'leaf'],
        morphInterval,
      );
      sequence.start();
    }

    // ── RAF loop ────────────────────────────────────────────
    let rafId = null;
    let frameCount = 0;

    const tick = () => {
      rafId = requestAnimationFrame(tick);

      const delta   = clock.getDelta();
      const elapsed = clock.getElapsedTime();

      system.tick(elapsed, delta);
      renderer.render(scene, camera);

      frameCount++;
      if (frameCount === 1 || frameCount % 60 === 0) {
        console.log('[ParticleCanvas] Rendering frame', frameCount, 'particles:', system._count);
      }
    };

    tick();

    // ── ResizeObserver ───────────────────────────────────────
    const resizeObserver = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const { inlineSize: rw, blockSize: rh } =
          entry.contentBoxSize?.[0] ?? {
            inlineSize: entry.contentRect.width,
            blockSize : entry.contentRect.height,
          };

        const safeW = Math.max(1, rw);
        const safeH = Math.max(1, rh);

        camera.aspect = safeW / safeH;
        camera.updateProjectionMatrix();
        renderer.setSize(safeW, safeH, false);
        renderer.setPixelRatio(Math.min(window.devicePixelRatio, PIXEL_RATIO_CAP));
        system.resize(safeW, safeH);
      }
    });

    if (parent) resizeObserver.observe(parent);

    // ── Cleanup ──────────────────────────────────────────────
    return () => {
      if (rafId !== null) cancelAnimationFrame(rafId);
      resizeObserver.disconnect();
      sequence?.stop();
      system.dispose();
      renderer.dispose();
      _systemRef.current = null;
      if (systemRef) systemRef.current = null;
    };
  }, []); // mount once

  return (
    <canvas
      ref={canvasRef}
      className={`particle-canvas ${className}`}
      aria-hidden="true"
    />
  );
}