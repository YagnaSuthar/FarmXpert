'use client';

// ============================================================
// FILE: src/reusablefiles/graphs/use-chart-size.js
//
// Measures the box a chart is rendered into so the SVG viewBox can be
// declared in the SAME units as the rendered pixels.
//
// Why it matters: a viewBox narrower than its container is scaled up,
// and SVG scales text with everything else — an 11px axis label in a
// 640-unit viewBox renders at 20px inside a 1150px card. Matching the
// viewBox to the measured width keeps 1 user unit = 1 CSS pixel, so
// every chart's typography is identical at every breakpoint.
// ============================================================

import { useEffect, useLayoutEffect, useRef, useState } from 'react';

// Measuring before paint keeps the chart from rendering once at the
// fallback width and then snapping — which would otherwise be visible
// as a jump at the start of the entrance animation. useLayoutEffect
// does not exist during SSR, so fall back to useEffect there.
const useIsomorphicLayoutEffect =
  typeof window !== 'undefined' ? useLayoutEffect : useEffect;

/**
 * @param {number} fallback width used before the first measurement
 * @param {number} min      floor, so an unlaid-out box cannot collapse
 *                          the geometry (sparklines need a low one —
 *                          they live inside narrow stat cards)
 * @returns {[React.RefObject, number]} ref to attach, current width
 */
export default function useChartSize(fallback = 640, min = 280) {
  const ref = useRef(null);
  const [width, setWidth] = useState(fallback);

  useIsomorphicLayoutEffect(() => {
    const node = ref.current;
    if (!node) return undefined;

    const measure = () => {
      const w = Math.round(node.getBoundingClientRect().width);
      // Ignore 0 (display:none / not yet laid out) and sub-pixel noise.
      if (w > 0) setWidth((prev) => (Math.abs(prev - w) > 1 ? w : prev));
    };

    measure();

    if (typeof ResizeObserver === 'undefined') {
      window.addEventListener('resize', measure);
      return () => window.removeEventListener('resize', measure);
    }

    const ro = new ResizeObserver(measure);
    ro.observe(node);
    return () => ro.disconnect();
  }, []);

  return [ref, Math.max(min, width)];
}
