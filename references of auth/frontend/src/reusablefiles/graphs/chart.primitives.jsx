'use client';

// ============================================================
// FILE: src/reusablefiles/graphs/chart.primitives.jsx
//
// Small SVG building blocks shared by the cartesian charts:
// grid, axes, defs (hatch / gradients) and the HTML tooltip layer.
// Everything here is presentational — no data shaping.
// ============================================================

import React from 'react';
import { round } from './chart.utils';

/* -------------------------------------------------------------- grid */

/** Horizontal (and optionally vertical) grid lines across the plot box. */
export function Grid({ box, yTicks = [], yScale, xLines = [], vertical = false }) {
  return (
    <g className="graph-grid" aria-hidden="true">
      {yTicks.map((t) => (
        <line
          key={`h-${t}`}
          x1={box.x}
          x2={box.x + box.w}
          y1={round(yScale(t))}
          y2={round(yScale(t))}
          className="graph-grid-line"
        />
      ))}
      {vertical &&
        xLines.map((x, i) => (
          <line
            key={`v-${i}`}
            x1={round(x)}
            x2={round(x)}
            y1={box.y}
            y2={box.y + box.h}
            className="graph-grid-line"
          />
        ))}
    </g>
  );
}

/* -------------------------------------------------------------- axes */

/** Value axis down the left edge. */
export function YAxis({ box, ticks = [], scale, format = (v) => v }) {
  return (
    <g className="graph-axis graph-axis-y" aria-hidden="true">
      {ticks.map((t) => (
        <text
          key={t}
          x={box.x - 10}
          y={round(scale(t))}
          className="graph-axis-label"
          textAnchor="end"
          dominantBaseline="middle"
        >
          {format(t)}
        </text>
      ))}
    </g>
  );
}

/** Category axis along the bottom edge. */
export function XAxis({ box, items = [], rotate = 0 }) {
  return (
    <g className="graph-axis graph-axis-x" aria-hidden="true">
      {items.map((it, i) => (
        <text
          key={`${it.label}-${i}`}
          x={round(it.x)}
          y={box.y + box.h + 20}
          className="graph-axis-label"
          textAnchor={rotate ? 'end' : 'middle'}
          dominantBaseline="middle"
          transform={rotate ? `rotate(${rotate} ${round(it.x)} ${box.y + box.h + 20})` : undefined}
        >
          {it.label}
        </text>
      ))}
    </g>
  );
}

/* -------------------------------------------------------------- defs */

/**
 * Diagonal hatch used for de-emphasised bars, plus a vertical fade for
 * area fills. Ids must be unique per chart instance — pass `useId()`.
 */
export function ChartDefs({ id, areaColor }) {
  return (
    <defs>
      <pattern
        id={`hatch-${id}`}
        width="10"
        height="10"
        patternTransform="rotate(45)"
        patternUnits="userSpaceOnUse"
      >
        <rect width="10" height="10" style={{ fill: 'var(--graph-hatch-b)' }} />
        <rect width="5" height="10" style={{ fill: 'var(--graph-hatch-a)' }} />
      </pattern>

      <linearGradient id={`area-${id}`} x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stopColor={areaColor || 'var(--graph-series-1)'} stopOpacity="0.24" />
        <stop offset="100%" stopColor={areaColor || 'var(--graph-series-1)'} stopOpacity="0" />
      </linearGradient>
    </defs>
  );
}

/* --------------------------------------------------- series gradients */

/** Stable gradient id for series `i` within chart instance `id`. */
export const gradientId = (id, i) => `gs-${id}-${i}`;

/** Paint value to hand to `fill` / `stroke`. */
export const gradientFill = (id, i) => `url(#${gradientId(id, i)})`;

/**
 * One gradient per series color, so every filled mark in the family —
 * bars, wedges, boxes, arcs, dots — carries the same depth falloff
 * instead of reading as a flat block of color.
 *
 * The ramp is built FROM the series color itself using stop-opacity, so
 * it works unchanged with the `var(--graph-series-*)` tokens and can
 * never introduce a hue from outside the Frozen Lake palette.
 *
 * @param {string} id      chart instance id (a useId() value)
 * @param {string[]} colors one entry per series / mark
 * @param {'vertical'|'horizontal'|'diagonal'} direction
 * @param {'linear'|'radial'} kind  radial suits round marks (dots, wedges)
 * @param {[number, number]} range  opacity at the near and far stop
 */
export function SeriesGradients({
  id,
  colors = [],
  direction = 'vertical',
  kind = 'linear',
  range = [1, 0.42],
}) {
  const vec =
    direction === 'horizontal'
      ? { x1: '0', y1: '0', x2: '1', y2: '0' }
      : direction === 'diagonal'
        ? { x1: '0', y1: '0', x2: '1', y2: '1' }
        : { x1: '0', y1: '0', x2: '0', y2: '1' };

  const [near, far] = range;
  const mid = far + (near - far) * 0.62;

  return (
    <defs>
      {colors.map((color, i) =>
        kind === 'radial' ? (
          <radialGradient key={i} id={gradientId(id, i)} cx="34%" cy="28%" r="82%">
            <stop offset="0%" stopColor={color} stopOpacity={near} />
            <stop offset="100%" stopColor={color} stopOpacity={far} />
          </radialGradient>
        ) : (
          <linearGradient key={i} id={gradientId(id, i)} {...vec}>
            <stop offset="0%" stopColor={color} stopOpacity={near} />
            <stop offset="58%" stopColor={color} stopOpacity={mid} />
            <stop offset="100%" stopColor={color} stopOpacity={far} />
          </linearGradient>
        ),
      )}
    </defs>
  );
}

/* ----------------------------------------------------------- tooltip */

/**
 * HTML tooltip positioned in percentage units so it tracks the SVG
 * through any responsive scale. Rendered above the chart, never inside
 * the SVG — SVG has no text wrapping.
 */
export function ChartTooltip({ open, xPct, yPct, title, rows = [] }) {
  if (!open) return null;
  return (
    <div
      className="graph-tooltip"
      style={{ left: `${xPct}%`, top: `${yPct}%` }}
      role="presentation"
    >
      {title ? <span className="graph-tooltip-title">{title}</span> : null}
      {rows.map((r, i) => (
        <span className="graph-tooltip-row" key={`${r.label}-${i}`}>
          {r.color ? <i className="graph-tooltip-dot" style={{ background: r.color }} /> : null}
          <span className="graph-tooltip-key">{r.label}</span>
          <b className="graph-tooltip-val">{r.value}</b>
        </span>
      ))}
    </div>
  );
}
