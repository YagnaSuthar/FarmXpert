'use client';

// ============================================================
// FILE: src/reusablefiles/graphs/ChartFrame.jsx
//
// The shell every chart in this folder renders into.
//
//  - keeps one responsive <svg viewBox> contract for the whole family
//  - renders the shared empty state when a chart receives no data
//  - hosts the HTML tooltip layer above the SVG
//
// It renders no marks of its own: charts pass their geometry as
// children and receive the plot box back through a render callback.
// ============================================================

import React from 'react';

/**
 * @param {object}   props
 * @param {number}   [props.width]   viewBox width  (user units)
 * @param {number}   [props.height]  viewBox height (user units)
 * @param {boolean}  [props.isEmpty] render the empty state instead of children
 * @param {string}   [props.emptyLabel]
 * @param {string}   [props.ariaLabel] accessible summary of the chart
 * @param {React.ReactNode} [props.tooltip] HTML tooltip layer
 * @param {string}   [props.className]
 * @param {'none'|'fixed'} [props.sizing] `fixed` keeps the SVG's own aspect
 */
export default function ChartFrame({
  width = 640,
  height = 260,
  isEmpty = false,
  emptyLabel = '—',
  ariaLabel,
  tooltip = null,
  className = '',
  children,
  ...rest
}) {
  if (isEmpty) {
    return (
      <div className={`graph-frame graph-frame-empty ${className}`.trim()} {...rest}>
        <span className="graph-empty-label">{emptyLabel}</span>
      </div>
    );
  }

  return (
    <div className={`graph-frame ${className}`.trim()} {...rest}>
      <svg
        className="graph-svg"
        viewBox={`0 0 ${width} ${height}`}
        preserveAspectRatio="xMidYMid meet"
        role="img"
        aria-label={ariaLabel}
      >
        {children}
      </svg>
      {tooltip}
    </div>
  );
}
