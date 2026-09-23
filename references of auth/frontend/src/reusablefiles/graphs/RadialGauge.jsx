'use client';

// ============================================================
// FILE: src/reusablefiles/graphs/RadialGauge.jsx
//
// Full-circle radial progress. Handles one ring or several concentric
// rings (an "activity rings" style comparison).
//
//   <RadialGauge value={72} caption={t('soilHealth')} />
//   <RadialGauge rings={[{label, value, max, color}, …]} />
// ============================================================

import React, { useId } from 'react';
import ChartLegend from './ChartLegend';
import { SeriesGradients, gradientFill } from './chart.primitives';
import { arcPath, clamp, seriesColor } from './chart.utils';

export default function RadialGauge({
  value = 0,
  max = 100,
  rings = null,
  size = 200,
  thickness = 16,
  gap = 8,
  startAngle = 0,
  label,
  caption,
  showLegend = false,
  gradient = true,
  formatValue = (v) => `${Math.round(v)}%`,
  ariaLabel,
  className = '',
}) {
  const uid = useId().replace(/:/g, '');
  const C = size / 2;
  const list = Array.isArray(rings) && rings.length
    ? rings.map((r, i) => ({
        label: r.label,
        color: r.color || seriesColor(i),
        pct: clamp((Number(r.value) / (Number(r.max) || 100)) * 100, 0, 100),
        raw: r.value,
      }))
    : [{
        label,
        color: 'var(--graph-series-1)',
        pct: clamp((Number(value) / (Number(max) || 1)) * 100, 0, 100),
        raw: value,
      }];

  const outerR = C - thickness / 2 - 2;

  return (
    <div className={`graph-gauge graph-gauge-radial ${className}`.trim()}>
      <div className="graph-gauge-wrap">
        <svg
          viewBox={`0 0 ${size} ${size}`}
          className="graph-gauge-svg"
          role="img"
          aria-label={ariaLabel}
        >
          {gradient && (
            <SeriesGradients
              id={uid}
              colors={list.map((r) => r.color)}
              direction="diagonal"
              range={[1, 0.5]}
            />
          )}

          {list.map((ring, i) => {
            const r = outerR - i * (thickness + gap);
            if (r <= thickness) return null;
            return (
              <g key={`${ring.label}-${i}`}>
                <circle
                  cx={C}
                  cy={C}
                  r={r}
                  className="graph-gauge-track"
                  style={{ strokeWidth: thickness }}
                />
                <path
                  d={arcPath(C, C, r, startAngle, startAngle + (ring.pct / 100) * 360)}
                  pathLength="1"
                  className="graph-gauge-band"
                  style={{ stroke: gradient ? gradientFill(uid, i) : ring.color, strokeWidth: thickness, '--i': i }}
                >
                  <title>{`${ring.label ?? ''} ${formatValue(ring.pct)}`.trim()}</title>
                </path>
              </g>
            );
          })}
        </svg>

        <div className="graph-gauge-mid">
          <b className="graph-gauge-value">{label ?? formatValue(list[0].pct)}</b>
          {caption ? <span className="graph-gauge-caption">{caption}</span> : null}
        </div>
      </div>

      {showLegend && list.length > 1 ? (
        <ChartLegend
          items={list.map((r) => ({ label: r.label, color: r.color, value: formatValue(r.pct) }))}
        />
      ) : null}
    </div>
  );
}
