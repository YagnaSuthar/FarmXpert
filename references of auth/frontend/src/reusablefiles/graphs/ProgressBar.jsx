'use client';

// ============================================================
// FILE: src/reusablefiles/graphs/ProgressBar.jsx
//
// Linear progress. Either a single `value` against `max`, or
// `segments = [{ label, value, color? }]` for a composition bar.
// Rendered as DOM (not SVG) so it inherits the card's type scale.
// ============================================================

import React from 'react';
import { clamp, seriesColor, sum } from './chart.utils';

export default function ProgressBar({
  value = 0,
  max = 100,
  segments = null,
  label,
  caption,
  showValue = true,
  size = 'md',
  color,
  formatValue = (v) => `${Math.round(v)}%`,
  className = '',
}) {
  const parts = Array.isArray(segments) && segments.length
    ? segments.map((s, i) => ({ ...s, value: Number(s.value) || 0, color: s.color || seriesColor(i) }))
    : null;

  const total = parts ? sum(parts.map((p) => p.value)) || 1 : Number(max) || 1;
  const pct = parts ? 100 : clamp((Number(value) / total) * 100, 0, 100);

  return (
    <div className={`graph-progress graph-progress-${size} ${className}`.trim()}>
      {(label || showValue) && (
        <div className="graph-progress-head">
          {label ? <span className="graph-progress-label">{label}</span> : <span />}
          {showValue && (
            <b className="graph-progress-value">
              {parts ? formatValue(total) : formatValue(pct)}
            </b>
          )}
        </div>
      )}

      <div
        className="graph-progress-track"
        role="progressbar"
        aria-valuenow={parts ? undefined : Math.round(pct)}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={label}
      >
        {parts ? (
          parts.map((p, i) => (
            <span
              key={`${p.label}-${i}`}
              className="graph-progress-fill"
              style={{ width: `${(p.value / total) * 100}%`, backgroundColor: p.color }}
              title={`${p.label}: ${p.value}`}
            />
          ))
        ) : (
          <span
            className="graph-progress-fill"
            style={{ width: `${pct}%`, backgroundColor: color || 'var(--graph-series-1)' }}
          />
        )}
      </div>

      {caption ? <span className="graph-progress-caption">{caption}</span> : null}
    </div>
  );
}
