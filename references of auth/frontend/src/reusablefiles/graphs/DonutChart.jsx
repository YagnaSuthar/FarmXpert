'use client';

// ============================================================
// FILE: src/reusablefiles/graphs/DonutChart.jsx
//
// Ring (or pie) breakdown of a whole.
//   data = [{ label, value, color? }]
//
// `PieChart` is the same renderer with the hole closed.
// ============================================================

import React, { useId, useMemo, useState } from 'react';
import ChartLegend from './ChartLegend';
import { SeriesGradients, gradientFill } from './chart.primitives';
import { normalizeSeries, seriesColor, sum, wedgePath } from './chart.utils';

export default function DonutChart({
  data = [],
  size = 220,
  thickness = 34,
  padAngle = 1.4,
  centerLabel,
  centerCaption,
  showLegend = true,
  legendAlign = 'center',
  gradient = true,
  formatValue = (v) => v,
  ariaLabel,
  emptyLabel = '—',
  className = '',
}) {
  const uid = useId().replace(/:/g, '');
  const [hover, setHover] = useState(-1);

  const rows = useMemo(() => {
    const norm = normalizeSeries(data).filter((d) => d.value > 0);
    return norm.map((d, i) => ({ ...d, color: d.color || seriesColor(i) }));
  }, [data]);

  const total = sum(rows.map((r) => r.value));
  const C = size / 2;
  const rOuter = C - 4;
  const rInner = Math.max(0, rOuter - thickness);

  if (!rows.length || total <= 0) {
    return (
      <div className={`graph-gauge graph-gauge-donut ${className}`.trim()}>
        <div className="graph-frame graph-frame-empty" style={{ minHeight: size }}>
          <span className="graph-empty-label">{emptyLabel}</span>
        </div>
      </div>
    );
  }

  // Cumulative angles are built in one pass and never mutated afterwards.
  const wedges = rows.reduce((acc, r) => {
    const start = acc.length ? acc[acc.length - 1].cursor : 0;
    const span = (r.value / total) * 360;
    const from = start + padAngle / 2;
    const to = start + span - padAngle / 2;
    acc.push({
      ...r,
      from,
      to: Math.max(from, to),
      cursor: start + span,
      pct: (r.value / total) * 100,
    });
    return acc;
  }, []);

  const focus = hover > -1 ? wedges[hover] : null;

  return (
    <div className={`graph-gauge graph-gauge-donut ${className}`.trim()}>
      <div className="graph-gauge-wrap" style={{ maxWidth: size }}>
        <svg
          viewBox={`0 0 ${size} ${size}`}
          className="graph-gauge-svg"
          role="img"
          aria-label={ariaLabel}
        >
          {gradient && (
            <SeriesGradients id={uid} colors={wedges.map((w) => w.color)} direction="diagonal" />
          )}
          {wedges.map((w, i) => (
            <path
              key={`${w.label}-${i}`}
              d={wedgePath(C, C, rOuter, rInner, w.from, w.to)}
              style={{ fill: gradient ? gradientFill(uid, i) : w.color, '--i': i }}
              className={
                'graph-donut-slice' +
                (hover > -1 && hover !== i ? ' is-dimmed' : '') +
                (hover === i ? ' is-active' : '')
              }
              onMouseEnter={() => setHover(i)}
              onMouseLeave={() => setHover(-1)}
            >
              <title>{`${w.label}: ${formatValue(w.value)}`}</title>
            </path>
          ))}
        </svg>

        {rInner > 0 && (
          <div className="graph-gauge-mid">
            <b className="graph-gauge-value">
              {focus ? formatValue(focus.value) : centerLabel ?? formatValue(total)}
            </b>
            {(focus?.label || centerCaption) && (
              <span className="graph-gauge-caption">{focus ? focus.label : centerCaption}</span>
            )}
          </div>
        )}
      </div>

      {showLegend && (
        <ChartLegend
          align={legendAlign}
          items={wedges.map((w) => ({
            label: w.label,
            color: w.color,
            value: formatValue(w.value),
          }))}
          activeIndex={hover}
        />
      )}
    </div>
  );
}

/** Same renderer with the hole closed. */
export function PieChart({ size = 220, ...rest }) {
  return <DonutChart size={size} thickness={size / 2} {...rest} />;
}
