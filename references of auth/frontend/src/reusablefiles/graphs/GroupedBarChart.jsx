'use client';

// ============================================================
// FILE: src/reusablefiles/graphs/GroupedBarChart.jsx
//
// Multi-series bars, side by side or stacked.
//   categories = ['Jan', 'Feb', …]
//   series     = [{ name, color?, data: [n, n, …] }]
//
// `StackedBarChart` is the same renderer with `stacked` pinned on.
// ============================================================

import React, { useId, useMemo, useState } from 'react';
import ChartFrame from './ChartFrame';
import useChartSize from './use-chart-size';
import {
  Grid, XAxis, YAxis, ChartDefs, ChartTooltip, SeriesGradients, gradientFill,
} from './chart.primitives';
import { niceTicks, roundedRect, round, scaleBand, scaleLinear, seriesColor, sum } from './chart.utils';

export default function GroupedBarChart({
  categories = [],
  series = [],
  stacked = false,
  width: widthProp,
  height = 280,
  showGrid = true,
  showAxis = true,
  barRadius = 6,
  gradient = true,
  tickCount = 4,
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

  const valid = useMemo(
    () => series.filter((s) => Array.isArray(s?.data) && s.data.length),
    [series],
  );
  const isEmpty = !categories.length || !valid.length;

  const pad = { t: 14, r: 12, b: 34, l: showAxis ? 42 : 8 };
  const box = {
    x: pad.l,
    y: pad.t,
    w: Math.max(10, width - pad.l - pad.r),
    h: Math.max(10, height - pad.t - pad.b),
  };

  const columnTotals = categories.map((_, ci) =>
    stacked
      ? sum(valid.map((s) => Number(s.data[ci]) || 0))
      : Math.max(...valid.map((s) => Number(s.data[ci]) || 0), 0),
  );
  const { ticks, max } = niceTicks(0, Math.max(...columnTotals, 0), tickCount);

  const y = scaleLinear([0, max], [box.y + box.h, box.y]);
  const outer = scaleBand(categories.length, [box.x, box.x + box.w], 0.34);
  const innerWidth = stacked ? outer.band : outer.band / valid.length;

  const colorOf = (s, i) => s.color || seriesColor(i);
  // paint = the gradient ramp; colorOf stays the raw value for legends/tooltips
  const paintOf = (s, i) => (gradient ? gradientFill(uid, i) : colorOf(s, i));

  const hoverRows =
    hover > -1
      ? valid.map((s, si) => ({
          label: s.name,
          value: formatValue(Number(s.data[hover]) || 0),
          color: colorOf(s, si),
        }))
      : [];

  return (
    <div ref={hostRef} className="graph-host">
      <ChartFrame
      width={width}
      height={height}
      isEmpty={isEmpty}
      emptyLabel={emptyLabel}
      ariaLabel={ariaLabel}
      className={`graph-grouped ${className}`.trim()}
      tooltip={
        <ChartTooltip
          open={hover > -1}
          xPct={((outer.at(hover) + outer.band / 2) / width) * 100}
          yPct={(y(columnTotals[hover] || 0) / height) * 100}
          title={categories[hover]}
          rows={hoverRows}
        />
      }
    >
      <ChartDefs id={uid} />
      {gradient && <SeriesGradients id={uid} colors={valid.map(colorOf)} />}

      {showGrid && <Grid box={box} yTicks={ticks} yScale={y} />}
      {showAxis && <YAxis box={box} ticks={ticks} scale={y} format={formatValue} />}

      <g className="graph-bars">
        {categories.map((cat, ci) => {
          const isDim = hover > -1 && hover !== ci;
          let stackTop = box.y + box.h;

          return (
            <g
              key={`${cat}-${ci}`}
              className={`graph-bar-group${isDim ? ' is-dimmed' : ''}`}
              style={{ '--i': ci }}
              onMouseEnter={() => setHover(ci)}
              onMouseLeave={() => setHover(-1)}
            >
              {/* transparent hit area so hovering the gap still works */}
              <rect
                x={round(outer.at(ci) - (outer.step - outer.band) / 2)}
                y={box.y}
                width={round(outer.step)}
                height={box.h}
                className="graph-hit-area"
              />
              {valid.map((s, si) => {
                const v = Number(s.data[ci]) || 0;
                if (stacked) {
                  const h = box.y + box.h - y(v);
                  const top = stackTop - h;
                  stackTop = top;
                  const isTop = si === valid.length - 1;
                  return (
                    <path
                      key={`${s.name}-${si}`}
                      d={roundedRect(outer.at(ci), top, innerWidth, h, isTop ? barRadius : 0)}
                      style={{ fill: paintOf(s, si) }}
                      className="graph-bar-rect"
                    >
                      <title>{`${cat} · ${s.name}: ${formatValue(v)}`}</title>
                    </path>
                  );
                }
                const top = y(v);
                const h = box.y + box.h - top;
                return (
                  <path
                    key={`${s.name}-${si}`}
                    d={roundedRect(outer.at(ci) + si * innerWidth, top, innerWidth * 0.82, h, barRadius)}
                    style={{ fill: paintOf(s, si) }}
                    className="graph-bar-rect"
                  >
                    <title>{`${cat} · ${s.name}: ${formatValue(v)}`}</title>
                  </path>
                );
              })}
            </g>
          );
        })}
      </g>

      {showAxis && (
        <XAxis
          box={box}
          items={categories.map((label, i) => ({ label, x: outer.at(i) + outer.band / 2 }))}
        />
      )}
      </ChartFrame>
    </div>
  );
}

/** Same renderer, stacking forced on. */
export function StackedBarChart(props) {
  return <GroupedBarChart {...props} stacked />;
}
