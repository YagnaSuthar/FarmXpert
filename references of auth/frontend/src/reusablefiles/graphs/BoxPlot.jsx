'use client';

// ============================================================
// FILE: src/reusablefiles/graphs/BoxPlot.jsx
//
// Box-and-whisker plot over one or more distributions.
//   groups = [{ label, values: [n, …], color? }]
//
// Each box shows Q1–Q3 with the median rule inside it; whiskers run to
// the furthest point inside 1.5 x IQR and anything past that is drawn
// as an outlier dot. Stats come from `boxStats()` in chart.utils.
// ============================================================

import React, { useId, useMemo, useState } from 'react';
import ChartFrame from './ChartFrame';
import useChartSize from './use-chart-size';
import {
  Grid, XAxis, YAxis, ChartTooltip, SeriesGradients, gradientFill,
} from './chart.primitives';
import { boxStats, niceTicks, round, scaleBand, scaleLinear, seriesColor } from './chart.utils';

export default function BoxPlot({
  groups = [],
  width: widthProp,
  height = 300,
  showGrid = true,
  showAxis = true,
  showOutliers = true,
  gradient = true,
  tickCount = 4,
  formatValue = (v) => v,
  labels = {},
  ariaLabel,
  emptyLabel = '—',
  className = '',
}) {
  const uid = useId().replace(/:/g, '');
  const [hover, setHover] = useState(-1);
  // viewBox width == rendered px, so axis type never scales with the card
  const [hostRef, measured] = useChartSize();
  const width = widthProp || measured;

  const stats = useMemo(
    () =>
      groups
        .map((g, i) => {
          const s = boxStats(g?.values);
          return s ? { ...s, label: g.label, color: g.color || seriesColor(i) } : null;
        })
        .filter(Boolean),
    [groups],
  );

  const pad = { t: 16, r: 16, b: 34, l: showAxis ? 46 : 10 };
  const box = {
    x: pad.l,
    y: pad.t,
    w: Math.max(10, width - pad.l - pad.r),
    h: Math.max(10, height - pad.t - pad.b),
  };

  const lows = stats.map((s) => Math.min(s.whiskerLow, ...(s.outliers.length ? s.outliers : [s.whiskerLow])));
  const highs = stats.map((s) => Math.max(s.whiskerHigh, ...(s.outliers.length ? s.outliers : [s.whiskerHigh])));
  const { ticks, min, max } = niceTicks(
    Math.min(...(lows.length ? lows : [0])),
    Math.max(...(highs.length ? highs : [1])),
    tickCount,
  );

  const y = scaleLinear([min, max], [box.y + box.h, box.y]);
  const band = scaleBand(stats.length, [box.x, box.x + box.w], 0.52);
  const boxW = Math.min(band.band, 74);

  const focus = hover > -1 ? stats[hover] : null;

  return (
    <div ref={hostRef} className="graph-host">
      <ChartFrame
      width={width}
      height={height}
      isEmpty={!stats.length}
      emptyLabel={emptyLabel}
      ariaLabel={ariaLabel}
      className={`graph-box ${className}`.trim()}
      tooltip={
        <ChartTooltip
          open={!!focus}
          xPct={focus ? ((band.at(hover) + band.band / 2) / width) * 100 : 0}
          yPct={focus ? (y(focus.q3) / height) * 100 : 0}
          title={focus?.label}
          rows={
            focus
              ? [
                  { label: labels.max || 'max', value: formatValue(round(focus.whiskerHigh, 2)) },
                  { label: labels.q3 || 'Q3', value: formatValue(round(focus.q3, 2)) },
                  { label: labels.median || 'median', value: formatValue(round(focus.median, 2)) },
                  { label: labels.q1 || 'Q1', value: formatValue(round(focus.q1, 2)) },
                  { label: labels.min || 'min', value: formatValue(round(focus.whiskerLow, 2)) },
                ]
              : []
          }
        />
      }
    >
      {gradient && <SeriesGradients id={uid} colors={stats.map((g) => g.color)} />}

      {showGrid && <Grid box={box} yTicks={ticks} yScale={y} />}
      {showAxis && <YAxis box={box} ticks={ticks} scale={y} format={formatValue} />}

      {stats.map((s, i) => {
        const cx = band.at(i) + band.band / 2;
        const left = cx - boxW / 2;
        const top = y(s.q3);
        const h = Math.max(1, y(s.q1) - y(s.q3));
        const isDim = hover > -1 && hover !== i;

        return (
          <g
            key={`${s.label}-${i}`}
            className={`graph-box-group${isDim ? ' is-dimmed' : ''}`}
            style={{ '--i': i }}
            onMouseEnter={() => setHover(i)}
            onMouseLeave={() => setHover(-1)}
          >
            {/* whisker stem + caps */}
            <line
              x1={round(cx)} x2={round(cx)}
              y1={round(y(s.whiskerHigh))} y2={round(y(s.whiskerLow))}
              className="graph-box-whisker"
            />
            <line
              x1={round(cx - boxW / 4)} x2={round(cx + boxW / 4)}
              y1={round(y(s.whiskerHigh))} y2={round(y(s.whiskerHigh))}
              className="graph-box-whisker"
            />
            <line
              x1={round(cx - boxW / 4)} x2={round(cx + boxW / 4)}
              y1={round(y(s.whiskerLow))} y2={round(y(s.whiskerLow))}
              className="graph-box-whisker"
            />

            {/* interquartile box */}
            <rect
              x={round(left)}
              y={round(top)}
              width={round(boxW)}
              height={round(h)}
              rx="6"
              style={{ fill: gradient ? gradientFill(uid, i) : s.color }}
              className="graph-box-rect"
            />

            {/* median rule */}
            <line
              x1={round(left)} x2={round(left + boxW)}
              y1={round(y(s.median))} y2={round(y(s.median))}
              className="graph-box-median"
            />

            {showOutliers &&
              s.outliers.map((o, oi) => (
                <circle
                  key={oi}
                  cx={round(cx)}
                  cy={round(y(o))}
                  r="3.2"
                  className="graph-box-outlier"
                >
                  <title>{formatValue(round(o, 2))}</title>
                </circle>
              ))}

            <title>{`${s.label} · n=${s.count}`}</title>
          </g>
        );
      })}

      {showAxis && (
        <XAxis
          box={box}
          items={stats.map((s, i) => ({ label: s.label, x: band.at(i) + band.band / 2 }))}
        />
      )}
      </ChartFrame>
    </div>
  );
}
