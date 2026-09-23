'use client';

// ============================================================
// FILE: src/reusablefiles/graphs/Sparkline.jsx
//
// Axis-less micro trend line for stat cards and table cells.
//   <Sparkline data={[4, 9, 6, 12, 11]} area />
// `variant="bars"` renders the same series as micro columns.
//
// Like the cartesian charts, the viewBox is measured rather than fixed.
// That matters more here than anywhere else: a 120-unit viewBox stretched
// across a 260px card scales x by ~2.2 and y by ~0.8, and a stroke drawn
// through that non-uniform transform no longer matches the path length
// the browser normalised for `pathLength` — which shows up as a BREAK in
// the line partway along. Measuring keeps the transform at 1:1 and the
// curve continuous.
// ============================================================

import React, { useId } from 'react';
import useChartSize from './use-chart-size';
import { areaPath, linePath, round, scaleBand, scaleLinear } from './chart.utils';

export default function Sparkline({
  data = [],
  width: widthProp,
  height = 36,
  area = false,
  curve = 'smooth',
  variant = 'line',
  color = 'var(--graph-series-1)',
  strokeWidth = 2,
  showLast = false,
  ariaLabel,
  className = '',
}) {
  const uid = useId().replace(/:/g, '');
  // low floor: this lives inside a stat card, not a full-width panel
  const [hostRef, measured] = useChartSize(120, 40);
  const width = widthProp || measured;

  const values = data.map(Number).filter(Number.isFinite);

  // The host carries the exact pixel height the viewBox declares, so the
  // rendered box and the viewBox stay 1:1 in both axes.
  const host = (children) => (
    <div ref={hostRef} className={`graph-spark-host ${className}`.trim()} style={{ height }}>
      {children}
    </div>
  );

  if (values.length < 1) return host(null);

  const inset = strokeWidth + 1;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const y = scaleLinear([min === max ? min - 1 : min, max], [height - inset, inset]);

  if (variant === 'bars') {
    const band = scaleBand(values.length, [0, width], 0.36);
    const zero = scaleLinear([Math.min(0, min), max], [height, inset]);
    return host(
      <svg
        className="graph-spark"
        viewBox={`0 0 ${width} ${height}`}
        preserveAspectRatio="none"
        role="img"
        aria-label={ariaLabel}
      >
        {values.map((v, i) => (
          <rect
            key={i}
            x={round(band.at(i))}
            y={round(zero(v))}
            width={round(band.band)}
            height={round(Math.max(1, height - zero(v)))}
            rx={round(Math.min(2.5, band.band / 2))}
            style={{ fill: color }}
          />
        ))}
      </svg>,
    );
  }

  const stepX = values.length > 1 ? width / (values.length - 1) : 0;
  const pts = values.map((v, i) => [values.length > 1 ? i * stepX : width / 2, y(v)]);

  return host(
    <svg
      className="graph-spark"
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="none"
      role="img"
      aria-label={ariaLabel}
    >
      {area && (
        <>
          <defs>
            <linearGradient id={`spark-${uid}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={color} stopOpacity="0.30" />
              <stop offset="100%" stopColor={color} stopOpacity="0" />
            </linearGradient>
          </defs>
          <path d={areaPath(pts, height, curve)} style={{ fill: `url(#spark-${uid})` }} />
        </>
      )}
      {/* pathLength normalises the path to 1 unit so the CSS draw-on
          animation works without measuring it in JS */}
      <path
        d={linePath(pts, curve)}
        pathLength="1"
        style={{ stroke: color, strokeWidth }}
        className="graph-spark-line"
      />
      {showLast && (
        <circle
          cx={round(pts[pts.length - 1][0])}
          cy={round(pts[pts.length - 1][1])}
          r={strokeWidth + 0.6}
          style={{ fill: color }}
        />
      )}
    </svg>,
  );
}
