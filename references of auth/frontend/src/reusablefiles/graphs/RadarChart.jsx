'use client';

// ============================================================
// FILE: src/reusablefiles/graphs/RadarChart.jsx
//
// Radar / spider chart for comparing several metrics on one scale.
//   axes   = [{ label, max? }]
//   series = [{ name, color?, data: [n, …] }]   // one value per axis
// ============================================================

import React, { useId, useMemo } from 'react';
import ChartLegend from './ChartLegend';
import { SeriesGradients, gradientFill } from './chart.primitives';
import { clamp, polar, round, seriesColor } from './chart.utils';

export default function RadarChart({
  axes = [],
  series = [],
  size = 300,
  levels = 4,
  max = 100,
  showLegend = true,
  gradient = true,
  formatValue = (v) => v,
  ariaLabel,
  emptyLabel = '—',
  className = '',
}) {
  const uid = useId().replace(/:/g, '');
  const C = size / 2;
  const R = C - 44;
  const n = axes.length;

  const valid = useMemo(
    () => series.filter((s) => Array.isArray(s?.data) && s.data.length),
    [series],
  );

  if (n < 3 || !valid.length) {
    return (
      <div className={`graph-frame graph-frame-empty ${className}`.trim()} style={{ minHeight: 160 }}>
        <span className="graph-empty-label">{emptyLabel}</span>
      </div>
    );
  }

  const angleAt = (i) => (360 / n) * i;
  const ringPath = (ratio) =>
    axes
      .map((_, i) => {
        const [x, y] = polar(C, C, R * ratio, angleAt(i));
        return `${i === 0 ? 'M' : 'L'} ${round(x)} ${round(y)}`;
      })
      .join(' ') + ' Z';

  const seriesPath = (s) =>
    s.data
      .slice(0, n)
      .map((v, i) => {
        const axisMax = axes[i]?.max ?? max;
        const ratio = clamp((Number(v) || 0) / (axisMax || 1), 0, 1);
        const [x, y] = polar(C, C, R * ratio, angleAt(i));
        return `${i === 0 ? 'M' : 'L'} ${round(x)} ${round(y)}`;
      })
      .join(' ') + ' Z';

  return (
    <div className={`graph-radar-wrap ${className}`.trim()}>
      <svg
        viewBox={`0 0 ${size} ${size}`}
        className="graph-svg"
        role="img"
        aria-label={ariaLabel}
      >
        {gradient && (
          <SeriesGradients
            id={uid}
            colors={valid.map((s, i) => s.color || seriesColor(i))}
            range={[0.34, 0.06]}
          />
        )}

        <g className="graph-radar-web" aria-hidden="true">
          {Array.from({ length: levels }, (_, l) => (
            <path key={l} d={ringPath((l + 1) / levels)} className="graph-radar-ring" />
          ))}
          {axes.map((_, i) => {
            const [x, y] = polar(C, C, R, angleAt(i));
            return (
              <line key={i} x1={C} y1={C} x2={round(x)} y2={round(y)} className="graph-radar-spoke" />
            );
          })}
        </g>

        {valid.map((s, si) => {
          const color = s.color || seriesColor(si);
          return (
            <g key={`${s.name}-${si}`}>
              <path
                d={seriesPath(s)}
                style={{ fill: gradient ? gradientFill(uid, si) : color, stroke: color }}
                className="graph-radar-area"
              />
              {s.data.slice(0, n).map((v, i) => {
                const axisMax = axes[i]?.max ?? max;
                const ratio = clamp((Number(v) || 0) / (axisMax || 1), 0, 1);
                const [x, y] = polar(C, C, R * ratio, angleAt(i));
                return (
                  <circle key={i} cx={round(x)} cy={round(y)} r="3.4" style={{ stroke: color }} className="graph-line-point">
                    <title>{`${axes[i]?.label} · ${s.name}: ${formatValue(v)}`}</title>
                  </circle>
                );
              })}
            </g>
          );
        })}

        <g className="graph-radar-labels" aria-hidden="true">
          {axes.map((a, i) => {
            const [x, y] = polar(C, C, R + 22, angleAt(i));
            const anchor = Math.abs(x - C) < 6 ? 'middle' : x > C ? 'start' : 'end';
            return (
              <text
                key={i}
                x={round(x)}
                y={round(y)}
                className="graph-axis-label"
                textAnchor={anchor}
                dominantBaseline="middle"
              >
                {a.label}
              </text>
            );
          })}
        </g>
      </svg>

      {showLegend && valid.length > 1 && (
        <ChartLegend items={valid.map((s, i) => ({ label: s.name, color: s.color || seriesColor(i) }))} />
      )}
    </div>
  );
}
