'use client';

// ============================================================
// FILE: src/reusablefiles/texture/GenerativeTexture.jsx
//
// Drops the generative curve-field behind any dark surface.
//
//   <Card tone="deep">
//     <GenerativeTexture variant="tracker" />
//     …content…
//   </Card>
//
// The parent supplies the gradient base (`.ui-card-deep`); this paints
// the linework on top of it. Repaints on resize (debounced) so the
// field always fills its box at the right density.
// ============================================================

import React, { useEffect, useRef } from 'react';
import { TEXTURE_PRESETS, paintTexture, readTexturePalette } from './texture.engine';

export default function GenerativeTexture({ variant = 'tracker', className = '' }) {
  const ref = useRef(null);

  useEffect(() => {
    const cv = ref.current;
    if (!cv) return undefined;

    const cfg = TEXTURE_PRESETS[variant] || TEXTURE_PRESETS.tracker;
    const paint = () => paintTexture(cv, cfg, readTexturePalette(cv));

    // Paint after layout so the canvas measures its real box.
    const raf = requestAnimationFrame(paint);

    let timer = null;
    const schedule = () => {
      clearTimeout(timer);
      timer = setTimeout(paint, 180);
    };

    // ResizeObserver catches grid reflow, not just window resizes.
    const ro = typeof ResizeObserver !== 'undefined' ? new ResizeObserver(schedule) : null;
    if (ro) ro.observe(cv);
    window.addEventListener('resize', schedule);

    return () => {
      cancelAnimationFrame(raf);
      clearTimeout(timer);
      if (ro) ro.disconnect();
      window.removeEventListener('resize', schedule);
    };
  }, [variant]);

  return <canvas ref={ref} className={`ui-texture ${className}`.trim()} aria-hidden="true" />;
}
