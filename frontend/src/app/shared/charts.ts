import { Point } from '../core/models';
import { EChartsCoreOption } from './echarts';
import { CHART_GRID, CHART_TEXT, colorFor } from './palette';

const MONO = 'JetBrains Mono, Consolas, monospace';
const RED = '#ff2a2a';

export interface LatencyChartOpts {
  hidden?: ReadonlySet<string>;
  threshold?: number;
}

export function latencyChart(
  series: Record<string, Point[]>,
  names: Record<string, string> = {},
  opts: LatencyChartOpts = {},
): EChartsCoreOption {
  const ids = Object.keys(series);
  const label = (id: string) => names[id] ?? id;
  const hidden = opts.hidden ?? new Set<string>();
  const threshold = opts.threshold ?? 100;
  return {
    animation: false,
    textStyle: { fontFamily: MONO },
    grid: { left: 8, right: 12, top: 52, bottom: 6, containLabel: true },
    legend: {
      data: ids.map(label),
      // El estado de la leyenda lo decide la consola, así aislar y ocultar no se pisan
      selected: Object.fromEntries(ids.map((id) => [label(id), !hidden.has(label(id))])),
      top: 0, left: 0, icon: 'rect', itemWidth: 14, itemHeight: 3, itemGap: 14,
      textStyle: { color: '#a9b1bd', fontFamily: MONO, fontSize: 10 },
      inactiveColor: '#46505f',
    },
    tooltip: {
      trigger: 'axis', backgroundColor: '#15181d', borderColor: '#46505f', borderRadius: 0,
      textStyle: { color: '#f2f4f7', fontFamily: MONO, fontSize: 11 },
      axisPointer: { type: 'line', lineStyle: { color: RED, width: 1 } },
      valueFormatter: (v: number) => `${v?.toFixed?.(1) ?? v} ms`,
    },
    xAxis: {
      type: 'time',
      axisLabel: { color: CHART_TEXT, fontFamily: MONO, fontSize: 10, hideOverlap: true },
      axisLine: { lineStyle: { color: '#46505f' } },
      axisTick: { lineStyle: { color: '#46505f' } },
      splitLine: { show: true, lineStyle: { color: CHART_GRID } },
    },
    yAxis: {
      type: 'value',
      axisLabel: { color: CHART_TEXT, fontFamily: MONO, fontSize: 10 },
      splitLine: { lineStyle: { color: CHART_GRID } },
    },
    series: [
      ...ids.map((id) => ({
        name: label(id),
        type: 'line',
        showSymbol: false,
        lineStyle: { width: 1.6 },
        color: colorFor(id),
        emphasis: { focus: 'series', lineStyle: { width: 2.4 } },
        data: series[id].map(([t, v]) => [t * 1000, v]),
      })),
      {
        name: 'Umbral',
        type: 'line',
        color: RED,
        data: [],
        markLine: {
          silent: true, symbol: 'none',
          lineStyle: { color: RED, type: 'dashed', width: 1 },
          label: { color: RED, fontFamily: MONO, fontSize: 10, formatter: `MAX ${threshold}` },
          data: [{ yAxis: threshold }],
        },
      },
    ],
  };
}

export function sparkline(points: Point[], color: string): EChartsCoreOption {
  return {
    animation: false,
    grid: { left: 0, right: 0, top: 4, bottom: 0 },
    xAxis: { type: 'time', show: false },
    yAxis: { type: 'value', show: false, scale: true },
    series: [
      {
        type: 'line',
        showSymbol: false,
        step: 'middle',
        color,
        lineStyle: { width: 1.4 },
        areaStyle: { color, opacity: 0.12 },
        data: points.map(([t, v]) => [t * 1000, v]),
      },
    ],
  };
}
