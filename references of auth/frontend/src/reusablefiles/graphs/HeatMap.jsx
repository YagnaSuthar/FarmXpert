'use client';

// ============================================================
// FILE: src/reusablefiles/graphs/HeatMap.jsx
//
// Matrix heat map (hour x weekday activity, sensor x zone readings…).
//   xLabels = ['00', '04', …]
//   yLabels = ['Mon', 'Tue', …]
//   matrix  = [[n, n, …], …]   // one row per yLabel
//
// Intensity is expressed as opacity over a single ramp color, which
// keeps the whole map inside the Frozen Lake family instead of
// introducing a second hue.
// ============================================================

import React, { useMemo, useState } from 'react';
import useChartSize from './use-chart-size';
import { clamp, round } from './chart.utils';

export default function HeatMap({
  matrix = [],
  xLabels = [],
  yLabels = [],
  color = 'var(--graph-series-1)',
  cellRadius = 4,
  gap = 3,
  maxCell = 34,
  min: minProp,
  max: maxProp,
  formatValue = (v) => v,
  ariaLabel,
  emptyLabel = '—',
  className = '',
}) {
  const [hover, setHover] = useState(null);
  // viewBox width == rendered px, so the labels never scale with the card
  const [hostRef, measured] = useChartSize();

  const flat = useMemo(
    () => matrix.flat().map(Number).filter(Number.isFinite),
    [matrix],
  );

  if (!matrix.length || !flat.length) {
    return (
      <div ref={hostRef} className={`graph-frame graph-frame-empty ${className}`.trim()}>
        <span className="graph-empty-label">{emptyLabel}</span>
      </div>
    );
  }

  const min = Number.isFinite(minProp) ? minProp : Math.min(...flat);
  const max = Number.isFinite(maxProp) ? maxProp : Math.max(...flat);
  const span = max - min || 1;

  const cols = Math.max(...matrix.map((r) => r.length));
  const rows = matrix.length;

  const padL = yLabels.length ? 44 : 0;
  const padB = xLabels.length ? 22 : 0;
  // The grid fills the measured width; cells stay square-ish but never
  // grow past `maxCell`, so a 7-column map does not become a billboard.
  const width = measured;
  const cellW = Math.max(18, (width - padL) / cols);
  const cellH = Math.min(cellW, maxCell);
  const height = rows * cellH + padB;

  return (
    <div ref={hostRef} className={`graph-heat ${className}`.trim()}>
      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="graph-svg"
        role="img"
        aria-label={ariaLabel}
      >
        {matrix.map((row, ri) =>
          row.map((raw, ci) => {
            const v = Number(raw);
            const t = Number.isFinite(v) ? clamp((v - min) / span, 0, 1) : 0;
            const isHover = hover && hover.r === ri && hover.c === ci;
            return (
              <rect
                key={`${ri}-${ci}`}
                x={round(padL + ci * cellW + gap / 2)}
                y={round(ri * cellH + gap / 2)}
                width={round(cellW - gap)}
                height={round(cellH - gap)}
                rx={cellRadius}
                /* ri + ci makes the entrance sweep diagonally */
                style={{ fill: color, opacity: 0.08 + t * 0.92, '--i': ri + ci }}
                className={`graph-heat-cell${isHover ? ' is-active' : ''}`}
                onMouseEnter={() => setHover({ r: ri, c: ci, v })}
                onMouseLeave={() => setHover(null)}
              >
                <title>{`${yLabels[ri] ?? ri} · ${xLabels[ci] ?? ci}: ${formatValue(v)}`}</title>
              </rect>
            );
          }),
        )}

        {yLabels.map((label, ri) => (
          <text
            key={`y-${ri}`}
            x={padL - 10}
            y={round(ri * cellH + cellH / 2)}
            className="graph-axis-label"
            textAnchor="end"
            dominantBaseline="middle"
          >
            {label}
          </text>
        ))}

        {xLabels.map((label, ci) => (
          <text
            key={`x-${ci}`}
            x={round(padL + ci * cellW + cellW / 2)}
            y={round(rows * cellH + 14)}
            className="graph-axis-label"
            textAnchor="middle"
            dominantBaseline="middle"
          >
            {label}
          </text>
        ))}
      </svg>
    </div>
  );
}
