'use client';

// ============================================================
// FILE: src/reusablefiles/graphs/LineChart.jsx
//
// Multi-series line chart with an optional gradient area fill and a
// snapping crosshair.
//   categories = ['Mon', 'Tue', …]
//   series     = [{ name, color?, data: [n, n, …], dashed?, area? }]
//
// `AreaChart` is the same renderer with the fill switched on.
// ============================================================

import React, { useId, useMemo, useState } from 'react';
import ChartFrame from './ChartFrame';
import useChartSize from './use-chart-size';
import { Grid, XAxis, YAxis, ChartTooltip } from './chart.primitives';
import { areaPath, linePath, niceTicks, round, scaleLinear, seriesColor } from './chart.utils';

export default function LineChart({
  categories = [],
  series = [],
  area = false,
  curve = 'smooth',
  width: widthProp,
  height = 260,
  showGrid = true,
  showAxis = true,
  showPoints = true,
  tickCount = 4,
  baseline = 0,
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

  const pad = { t: 16, r: 16, b: 32, l: showAxis ? 44 : 10 };
  const box = {
    x: pad.l,
    y: pad.t,
    w: Math.max(10, width - pad.l - pad.r),
    h: Math.max(10, height - pad.t - pad.b),
  };

  const allValues = valid.flatMap((s) => s.data.map(Number).filter(Number.isFinite));
  const { ticks, min, max } = niceTicks(
    Math.min(baseline, ...(allValues.length ? allValues : [0])),
    Math.max(...(allValues.length ? allValues : [1])),
    tickCount,
  );

  const y = scaleLinear([min, max], [box.y + box.h, box.y]);
  const stepX = categories.length > 1 ? box.w / (categories.length - 1) : 0;
  const xAt = (i) => (categories.length > 1 ? box.x + i * stepX : box.x + box.w / 2);

  const colorOf = (s, i) => s.color || seriesColor(i);

  // The capture rect spans exactly the plot box, so the pointer's
  // position inside it maps straight onto the category index.
  const onMove = (e) => {
    if (!categories.length) return;
    const r = e.currentTarget.getBoundingClientRect();
    if (!r.width) return;
    const t = (e.clientX - r.left) / r.width;
    const i = Math.round(t * (categories.length - 1));
    setHover(Math.max(0, Math.min(categories.length - 1, i)));
  };

  return (
    <div ref={hostRef} className="graph-host">
      <ChartFrame
      width={width}
      height={height}
      isEmpty={isEmpty}
      emptyLabel={emptyLabel}
      ariaLabel={ariaLabel}
      className={`graph-line ${className}`.trim()}
      tooltip={
        <ChartTooltip
          open={hover > -1}
          xPct={(xAt(hover) / width) * 100}
          yPct={(box.y / height) * 100}
          title={categories[hover]}
          rows={valid.map((s, si) => ({
            label: s.name,
            value: formatValue(Number(s.data[hover]) || 0),
            color: colorOf(s, si),
          }))}
        />
      }
    >
      <defs>
        {valid.map((s, si) => (
          <linearGradient key={si} id={`ln-area-${uid}-${si}`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={colorOf(s, si)} stopOpacity="0.26" />
            <stop offset="100%" stopColor={colorOf(s, si)} stopOpacity="0" />
          </linearGradient>
        ))}
      </defs>

      {showGrid && <Grid box={box} yTicks={ticks} yScale={y} />}
      {showAxis && <YAxis box={box} ticks={ticks} scale={y} format={formatValue} />}

      {valid.map((s, si) => {
        const pts = s.data
          .map((v, i) => [xAt(i), y(Number(v) || 0)])
          .filter(([, py]) => Number.isFinite(py));
        const wantsArea = s.area ?? area;

        return (
          <g key={`${s.name}-${si}`} className="graph-line-series">
            {wantsArea && (
              <path
                d={areaPath(pts, box.y + box.h, curve)}
                style={{ fill: `url(#ln-area-${uid}-${si})` }}
                className="graph-area-fill"
              />
            )}
            <path
              d={linePath(pts, curve)}
              /* a dashed series keeps its own dash pattern, so it must NOT
                 be normalised — it fades in instead of drawing */
              pathLength={s.dashed ? undefined : 1}
              style={{ stroke: colorOf(s, si) }}
              className={`graph-line-path${s.dashed ? ' is-dashed' : ''}`}
            />
            {showPoints &&
              pts.map(([px, py], i) => (
                <circle
                  key={i}
                  cx={round(px)}
                  cy={round(py)}
                  r={hover === i ? 5 : 3.2}
                  style={{ stroke: colorOf(s, si), '--i': i }}
                  className="graph-line-point"
                >
                  <title>{`${categories[i]} · ${s.name}: ${formatValue(Number(s.data[i]) || 0)}`}</title>
                </circle>
              ))}
          </g>
        );
      })}

      {hover > -1 && (
        <line
          x1={round(xAt(hover))}
          x2={round(xAt(hover))}
          y1={box.y}
          y2={box.y + box.h}
          className="graph-crosshair"
        />
      )}

      {/* pointer capture sits on top so moving across marks never flickers */}
      <rect
        x={box.x}
        y={box.y}
        width={box.w}
        height={box.h}
        className="graph-hit-area"
        onMouseMove={onMove}
        onMouseLeave={() => setHover(-1)}
      />

      {showAxis && (
        <XAxis box={box} items={categories.map((label, i) => ({ label, x: xAt(i) }))} />
      )}
      </ChartFrame>
    </div>
  );
}

/** Same renderer with the gradient fill switched on. */
export function AreaChart(props) {
  return <LineChart {...props} area />;
}
