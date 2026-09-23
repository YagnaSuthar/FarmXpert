'use client';

// ============================================================
// FILE: src/reusablefiles/graphs/BarChart.jsx
//
// Vertical or horizontal bar chart. Fully data driven:
//   data = [{ label, value, muted?, color? }]
// `muted` bars render with the diagonal hatch instead of a fill, which
// is how the reference design de-emphasises months without a target.
// ============================================================

import React, { useId, useMemo, useState } from 'react';
import ChartFrame from './ChartFrame';
import useChartSize from './use-chart-size';
import {
  Grid, XAxis, YAxis, ChartDefs, ChartTooltip, SeriesGradients, gradientFill,
} from './chart.primitives';
import {
  niceTicks, normalizeSeries, roundedRect, round,
  scaleBand, scaleLinear, seriesColor,
} from './chart.utils';

export default function BarChart({
  data = [],
  height = 260,
  width: widthProp,
  horizontal = false,
  showGrid = true,
  showValues = true,
  showAxis = true,
  barRadius = 999,
  tickCount = 4,
  colorByIndex = false,
  gradient = true,
  formatValue = (v) => v,
  ariaLabel,
  emptyLabel = '—',
  className = '',
}) {
  const uid = useId().replace(/:/g, '');
  const [hover, setHover] = useState(-1);
  // viewBox width == rendered px, so axis type never scales with the card
  const [hostRef, measured] = useChartSize();
  const width = widthProp || measured;
  const rows = useMemo(() => normalizeSeries(data), [data]);

  const pad = horizontal
    ? { t: 10, r: 40, b: 26, l: 96 }
    : { t: showValues ? 26 : 12, r: 12, b: 34, l: showAxis ? 42 : 8 };

  const box = {
    x: pad.l,
    y: pad.t,
    w: Math.max(10, width - pad.l - pad.r),
    h: Math.max(10, height - pad.t - pad.b),
  };

  const maxValue = rows.length ? Math.max(...rows.map((d) => d.value)) : 0;
  const { ticks, max } = niceTicks(0, maxValue, tickCount);

  const value = horizontal
    ? scaleLinear([0, max], [box.x, box.x + box.w])
    : scaleLinear([0, max], [box.y + box.h, box.y]);

  const band = scaleBand(
    rows.length,
    horizontal ? [box.y, box.y + box.h] : [box.x, box.x + box.w],
    horizontal ? 0.36 : 0.42,
  );

  // Flat color per bar — the source for both the gradient ramp and the
  // tooltip swatch, which needs the raw color rather than a paint url.
  const barColor = (row, i) =>
    row.color || (colorByIndex ? seriesColor(i) : 'var(--graph-series-1)');

  const barFill = (row, i) => {
    if (row.muted) return `url(#hatch-${uid})`;
    return gradient ? gradientFill(uid, i) : barColor(row, i);
  };

  const hovered = hover > -1 ? rows[hover] : null;
  const hoverPos = () => {
    if (!hovered) return { x: 0, y: 0 };
    return horizontal
      ? { x: (value(hovered.value) / width) * 100, y: ((band.at(hover) + band.band / 2) / height) * 100 }
      : { x: ((band.at(hover) + band.band / 2) / width) * 100, y: (value(hovered.value) / height) * 100 };
  };
  const pos = hoverPos();

  return (
    <div ref={hostRef} className="graph-host">
      <ChartFrame
      width={width}
      height={height}
      isEmpty={!rows.length}
      emptyLabel={emptyLabel}
      ariaLabel={ariaLabel}
      className={`graph-bar${horizontal ? ' graph-bar-h' : ''} ${className}`.trim()}
      tooltip={
        <ChartTooltip
          open={!!hovered}
          xPct={pos.x}
          yPct={pos.y}
          title={hovered?.label}
          rows={hovered ? [{ label: hovered.sublabel || '', value: formatValue(hovered.value), color: barColor(hovered, hover) }] : []}
        />
      }
    >
      <ChartDefs id={uid} />
      {gradient && (
        <SeriesGradients
          id={uid}
          colors={rows.map(barColor)}
          direction={horizontal ? 'horizontal' : 'vertical'}
        />
      )}

      {showGrid && !horizontal && (
        <Grid box={box} yTicks={ticks} yScale={value} />
      )}
      {showAxis && !horizontal && (
        <YAxis box={box} ticks={ticks} scale={value} format={formatValue} />
      )}

      <g className="graph-bars">
        {rows.map((row, i) => {
          const isDim = hover > -1 && hover !== i;

          if (horizontal) {
            const w = Math.max(0, value(row.value) - box.x);
            return (
              <g
                key={`${row.label}-${i}`}
                className={`graph-bar-group${isDim ? ' is-dimmed' : ''}`}
                style={{ '--i': i }}
                onMouseEnter={() => setHover(i)}
                onMouseLeave={() => setHover(-1)}
              >
                <text
                  x={box.x - 12}
                  y={round(band.at(i) + band.band / 2)}
                  className="graph-axis-label"
                  textAnchor="end"
                  dominantBaseline="middle"
                >
                  {row.label}
                </text>
                <rect
                  x={box.x}
                  y={round(band.at(i))}
                  width={box.w}
                  height={round(band.band)}
                  rx={round(Math.min(barRadius, band.band / 2))}
                  className="graph-bar-track"
                />
                <rect
                  x={box.x}
                  y={round(band.at(i))}
                  width={round(w)}
                  height={round(band.band)}
                  rx={round(Math.min(barRadius, band.band / 2))}
                  style={{ fill: barFill(row, i) }}
                  className="graph-bar-rect"
                />
                {showValues && (
                  <text
                    x={round(box.x + w + 8)}
                    y={round(band.at(i) + band.band / 2)}
                    className="graph-bar-value"
                    dominantBaseline="middle"
                  >
                    {formatValue(row.value)}
                  </text>
                )}
                <title>{`${row.label}: ${formatValue(row.value)}`}</title>
              </g>
            );
          }

          const top = value(row.value);
          const h = Math.max(0, box.y + box.h - top);
          return (
            <g
              key={`${row.label}-${i}`}
              className={`graph-bar-group${isDim ? ' is-dimmed' : ''}`}
              style={{ '--i': i }}
              onMouseEnter={() => setHover(i)}
              onMouseLeave={() => setHover(-1)}
            >
              {showValues && (
                <text
                  x={round(band.at(i) + band.band / 2)}
                  y={round(top - 10)}
                  className="graph-bar-value"
                  textAnchor="middle"
                >
                  {formatValue(row.value)}
                </text>
              )}
              <path
                d={roundedRect(band.at(i), top, band.band, h, Math.min(barRadius, band.band / 2))}
                style={{ fill: barFill(row, i) }}
                className={`graph-bar-rect${row.muted ? ' is-muted' : ''}`}
              />
              <title>{`${row.label}: ${formatValue(row.value)}`}</title>
            </g>
          );
        })}
      </g>

      {showAxis && !horizontal && (
        <XAxis
          box={box}
          items={rows.map((r, i) => ({ label: r.label, x: band.at(i) + band.band / 2 }))}
        />
      )}
      </ChartFrame>
    </div>
  );
}
