'use client';

// ============================================================
// FILE: src/reusablefiles/graphs/SemiCircleGauge.jsx
//
// Semi-circular (arc) progress gauge.
//
// Two ways to drive it:
//   1. segments = [{ label, value, color? }]  — a composition gauge
//   2. value + max                            — a single progress arc
//
// Segments are drawn largest-cumulative first so each round cap lands
// on top of the band behind it, which is what gives the stacked arc
// its layered look instead of butt-jointed slices.
// ============================================================

import React, { useId, useMemo } from 'react';
import ChartLegend from './ChartLegend';
import { SeriesGradients, gradientFill } from './chart.primitives';
import { arcPath, clamp, round, seriesColor, sum } from './chart.utils';

export default function SemiCircleGauge({
  segments = null,
  value = 0,
  max = 100,
  sweep = 250,
  thickness = 30,
  label,
  caption,
  showLegend = true,
  gradient = true,
  legendItems = null,
  formatValue = (v) => `${Math.round(v)}%`,
  ariaLabel,
  className = '',
}) {
  const uid = useId().replace(/:/g, '');

  // Geometry: R and CY are chosen so the arc ends plus half the stroke
  // still clear the 200-unit viewBox at a 250 degree sweep.
  const W = 260;
  const H = 200;
  const CX = 130;
  const CY = 118;
  const R = 84;

  const half = sweep / 2;
  const start = -half;

  const rows = useMemo(() => {
    if (!Array.isArray(segments)) return null;
    return segments
      .map((s, i) => ({ ...s, value: Number(s.value) || 0, color: s.color || seriesColor(i) }))
      .filter((s) => s.value >= 0);
  }, [segments]);

  const total = rows ? sum(rows.map((r) => r.value)) : 0;

  /* Cumulative arc ends, then reversed so the widest is painted first. */
  const bands = useMemo(() => {
    if (!rows || total <= 0) return [];
    let acc = 0;
    const out = rows.map((r) => {
      acc += r.value;
      return { ...r, end: start + (acc / total) * sweep };
    });
    return out.reverse();
  }, [rows, total, start, sweep]);

  const pct = rows
    ? (rows[0] ? (rows[0].value / (total || 1)) * 100 : 0)
    : clamp((Number(value) / (Number(max) || 1)) * 100, 0, 100);

  const singleEnd = start + (clamp(pct, 0, 100) / 100) * sweep;

  const legend =
    legendItems ||
    (rows ? rows.map((r) => ({ label: r.label, color: r.color, value: r.displayValue })) : null);

  return (
    <div className={`graph-gauge graph-gauge-semi ${className}`.trim()}>
      <div className="graph-gauge-wrap">
        <svg
          viewBox={`0 0 ${W} ${H}`}
          className="graph-gauge-svg"
          role="img"
          aria-label={ariaLabel}
        >
          {gradient && (
            <SeriesGradients
              id={uid}
              colors={bands.length ? bands.map((b) => b.color) : ['var(--graph-series-1)']}
              direction="horizontal"
              range={[1, 0.55]}
            />
          )}

          <path
            d={arcPath(CX, CY, R, start, start + sweep)}
            className="graph-gauge-track"
            style={{ strokeWidth: thickness }}
          />
          {bands.length
            ? bands.map((b, i) => (
                <path
                  key={`${b.label}-${i}`}
                  d={arcPath(CX, CY, R, start, b.end)}
                  pathLength="1"
                  className="graph-gauge-band"
                  style={{ stroke: gradient ? gradientFill(uid, i) : b.color, strokeWidth: thickness, '--i': i }}
                >
                  <title>{`${b.label}: ${b.value}`}</title>
                </path>
              ))
            : (
              <path
                d={arcPath(CX, CY, R, start, singleEnd)}
                pathLength="1"
                className="graph-gauge-band"
                style={{ stroke: gradient ? gradientFill(uid, 0) : 'var(--graph-series-1)', strokeWidth: thickness }}
              />
            )}
        </svg>

        <div className="graph-gauge-mid">
          <b className="graph-gauge-value">{label ?? formatValue(pct)}</b>
          {caption ? <span className="graph-gauge-caption">{caption}</span> : null}
        </div>
      </div>

      {showLegend && legend?.length ? <ChartLegend items={legend} /> : null}
    </div>
  );
}

/** Convenience alias for the single-value form. */
export function ArcProgress({ value, max = 100, ...rest }) {
  return <SemiCircleGauge value={value} max={max} showLegend={false} {...rest} />;
}

/** Exported so a caller can mirror the gauge's own rounding in a label. */
export const gaugePercent = (value, max = 100) => round(clamp((value / (max || 1)) * 100, 0, 100), 1);
