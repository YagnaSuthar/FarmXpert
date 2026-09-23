'use client';

// ============================================================
// FILE: src/reusablefiles/graphs/ScatterPlot.jsx
//
// X/Y scatter with an optional third dimension mapped to dot size
// (a bubble chart).
//   series = [{ name, color?, points: [{ x, y, r?, label? }] }]
// ============================================================

import React, { useId, useMemo, useState } from 'react';
import ChartFrame from './ChartFrame';
import useChartSize from './use-chart-size';
import {
  Grid, XAxis, YAxis, ChartTooltip, SeriesGradients, gradientFill,
} from './chart.primitives';
import { niceTicks, round, scaleLinear, seriesColor } from './chart.utils';

export default function ScatterPlot({
  series = [],
  width: widthProp,
  height = 300,
  showGrid = true,
  showAxis = true,
  tickCount = 4,
  dotRadius = 5,
  maxRadius = 18,
  gradient = true,
  xLabel,
  yLabel,
  formatX = (v) => v,
  formatY = (v) => v,
  ariaLabel,
  emptyLabel = '—',
  className = '',
}) {
  const uid = useId().replace(/:/g, '');
  const [hover, setHover] = useState(null);
  // viewBox width == rendered px, so axis type never scales with the card
  const [hostRef, measured] = useChartSize();
  const width = widthProp || measured;

  const valid = useMemo(
    () => series.filter((s) => Array.isArray(s?.points) && s.points.length),
    [series],
  );
  const all = valid.flatMap((s) => s.points);

  const pad = { t: 16, r: 18, b: showAxis ? 40 : 12, l: showAxis ? 48 : 12 };
  const box = {
    x: pad.l,
    y: pad.t,
    w: Math.max(10, width - pad.l - pad.r),
    h: Math.max(10, height - pad.t - pad.b),
  };

  const xs = all.map((p) => Number(p.x)).filter(Number.isFinite);
  const ys = all.map((p) => Number(p.y)).filter(Number.isFinite);
  const rs = all.map((p) => Number(p.r)).filter(Number.isFinite);

  const xt = niceTicks(Math.min(...(xs.length ? xs : [0])), Math.max(...(xs.length ? xs : [1])), tickCount);
  const yt = niceTicks(Math.min(...(ys.length ? ys : [0])), Math.max(...(ys.length ? ys : [1])), tickCount);

  const x = scaleLinear([xt.min, xt.max], [box.x, box.x + box.w]);
  const y = scaleLinear([yt.min, yt.max], [box.y + box.h, box.y]);
  const rMax = rs.length ? Math.max(...rs) : 0;
  const radius = (p) =>
    rMax > 0 && Number.isFinite(Number(p.r))
      ? Math.max(3, (Number(p.r) / rMax) * maxRadius)
      : dotRadius;

  return (
    <div ref={hostRef} className="graph-host">
      <ChartFrame
      width={width}
      height={height}
      isEmpty={!valid.length}
      emptyLabel={emptyLabel}
      ariaLabel={ariaLabel}
      className={`graph-scatter ${className}`.trim()}
      tooltip={
        <ChartTooltip
          open={!!hover}
          xPct={hover ? (x(hover.point.x) / width) * 100 : 0}
          yPct={hover ? (y(hover.point.y) / height) * 100 : 0}
          title={hover?.point.label || hover?.name}
          rows={
            hover
              ? [
                  { label: xLabel || 'x', value: formatX(hover.point.x), color: hover.color },
                  { label: yLabel || 'y', value: formatY(hover.point.y) },
                ]
              : []
          }
        />
      }
    >
      {gradient && (
        <SeriesGradients
          id={uid}
          colors={valid.map((s, i) => s.color || seriesColor(i))}
          kind="radial"
          range={[1, 0.5]}
        />
      )}

      {showGrid && <Grid box={box} yTicks={yt.ticks} yScale={y} vertical xLines={xt.ticks.map(x)} />}
      {showAxis && <YAxis box={box} ticks={yt.ticks} scale={y} format={formatY} />}

      {valid.map((s, si) => {
        const color = s.color || seriesColor(si);
        return (
          <g key={`${s.name}-${si}`} className="graph-scatter-series">
            {s.points.map((p, pi) => {
              if (!Number.isFinite(Number(p.x)) || !Number.isFinite(Number(p.y))) return null;
              const isDim = hover && hover.point !== p;
              return (
                <circle
                  key={pi}
                  cx={round(x(Number(p.x)))}
                  cy={round(y(Number(p.y)))}
                  r={round(radius(p))}
                  style={{ fill: gradient ? gradientFill(uid, si) : color, '--i': pi }}
                  className={`graph-scatter-dot${isDim ? ' is-dimmed' : ''}`}
                  onMouseEnter={() => setHover({ point: p, name: s.name, color })}
                  onMouseLeave={() => setHover(null)}
                >
                  <title>{`${p.label || s.name}: ${formatX(p.x)}, ${formatY(p.y)}`}</title>
                </circle>
              );
            })}
          </g>
        );
      })}

      {showAxis && (
        <XAxis box={box} items={xt.ticks.map((t) => ({ label: formatX(t), x: x(t) }))} />
      )}
      </ChartFrame>
    </div>
  );
}

/** Bubble chart is a scatter whose points carry an `r`. */
export function BubbleChart(props) {
  return <ScatterPlot {...props} />;
}
