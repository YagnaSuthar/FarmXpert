'use client';

// ============================================================
// FILE: src/reusablefiles/graphs/ChartLegend.jsx
//
// Data-driven legend shared by every chart that shows more than one
// series. Labels are supplied already translated by the caller — this
// component never holds user-facing copy of its own.
// ============================================================

import React from 'react';
import { seriesColor } from './chart.utils';

/**
 * @param {object} props
 * @param {Array<{label:string, color?:string, value?:string|number}>} props.items
 * @param {'dot'|'bar'} [props.marker]
 * @param {'center'|'start'} [props.align]
 * @param {(index:number)=>void} [props.onSelect] makes entries interactive
 * @param {number} [props.activeIndex] -1 for none
 */
export default function ChartLegend({
  items = [],
  marker = 'dot',
  align = 'center',
  onSelect,
  activeIndex = -1,
  className = '',
}) {
  if (!items.length) return null;

  const interactive = typeof onSelect === 'function';
  const Tag = interactive ? 'button' : 'span';

  return (
    <div
      className={`graph-legend graph-legend-${align} ${className}`.trim()}
      role={interactive ? 'group' : undefined}
    >
      {items.map((item, i) => (
        <Tag
          key={`${item.label}-${i}`}
          type={interactive ? 'button' : undefined}
          className={
            'graph-legend-item' +
            (interactive ? ' is-interactive' : '') +
            (activeIndex === i ? ' is-active' : '') +
            (activeIndex > -1 && activeIndex !== i ? ' is-dimmed' : '')
          }
          style={{ '--i': i }}
          onClick={interactive ? () => onSelect(i) : undefined}
        >
          <i
            className={`graph-legend-marker graph-legend-marker-${marker}`}
            style={{ background: item.color || seriesColor(i) }}
          />
          <span className="graph-legend-label">{item.label}</span>
          {item.value !== undefined && (
            <b className="graph-legend-value">{item.value}</b>
          )}
        </Tag>
      ))}
    </div>
  );
}
