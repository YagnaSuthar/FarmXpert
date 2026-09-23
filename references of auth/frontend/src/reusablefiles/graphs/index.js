// ============================================================
// FILE: src/reusablefiles/graphs/index.js
//
// Public surface of the chart family. Import from here, never from
// the individual files, so a chart can be re-implemented without
// touching its callers.
//
//   import { BarChart, SemiCircleGauge } from '@/reusablefiles/graphs';
//
// Every chart is pure SVG/DOM — no charting dependency — and takes its
// colors from the `--graph-*` tokens in globals.css.
// ============================================================

/* cartesian */
export { default as BarChart } from './BarChart';
export { default as GroupedBarChart, StackedBarChart } from './GroupedBarChart';
export { default as LineChart, AreaChart } from './LineChart';
export { default as BoxPlot } from './BoxPlot';
export { default as ScatterPlot, BubbleChart } from './ScatterPlot';
export { default as HeatMap } from './HeatMap';

/* radial */
export { default as SemiCircleGauge, ArcProgress, gaugePercent } from './SemiCircleGauge';
export { default as RadialGauge } from './RadialGauge';
export { default as DonutChart, PieChart } from './DonutChart';
export { default as RadarChart } from './RadarChart';

/* compact */
export { default as ProgressBar } from './ProgressBar';
export { default as Sparkline } from './Sparkline';

/* shared building blocks */
export { default as ChartFrame } from './ChartFrame';
export { default as ChartLegend } from './ChartLegend';
export {
  Grid, XAxis, YAxis, ChartDefs, ChartTooltip,
  SeriesGradients, gradientId, gradientFill,
} from './chart.primitives';

/* helpers — exported so pages can shape data with the same math */
export {
  SERIES,
  seriesColor,
  scaleLinear,
  scaleBand,
  niceTicks,
  linePath,
  areaPath,
  arcPath,
  wedgePath,
  polar,
  roundedRect,
  boxStats,
  quantile,
  formatCompact,
  formatNumber,
  normalizeSeries,
  clamp,
  round,
  sum,
} from './chart.utils';
