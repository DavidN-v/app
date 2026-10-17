import { Point } from '../core/models';
import { EChartsCoreOption } from './echarts';
import { CHART_GRID, CHART_TEXT, colorFor } from './palette';

export function latencyChart(series: Record<string, Point[]>, names: Record<string, string> = {}): EChartsCoreOption {
  return {
    animation: false,
    grid: { left: 8, right: 16, top: 64, bottom: 8, containLabel: true },
    legend: { top: 0, textStyle: { color: CHART_TEXT, fontFamily: 'Geist, system-ui' }, icon: 'rect', itemWidth: 10, itemHeight: 10 },
    tooltip: { trigger: 'axis', valueFormatter: (v: number) => `${v?.toFixed?.(1) ?? v} ms` },
    xAxis: {
      type: 'time',
      axisLabel: { color: CHART_TEXT },
      axisLine: { lineStyle: { color: CHART_GRID } },
      splitLine: { show: false },
    },
    yAxis: {
      type: 'value',
      axisLabel: { color: CHART_TEXT, formatter: '{value} ms' },
      splitLine: { lineStyle: { color: CHART_GRID } },
    },
    series: Object.entries(series).map(([id, points]) => ({
      name: names[id] ?? id,
      type: 'line',
      showSymbol: false,
      smooth: true,
      lineStyle: { width: 1.6 },
      color: colorFor(id),
      data: points.map(([t, v]) => [t * 1000, v]),
    })),
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
        smooth: true,
        color,
        lineStyle: { width: 1.5 },
        areaStyle: { opacity: 0.12 },
        data: points.map(([t, v]) => [t * 1000, v]),
      },
    ],
  };
}

export function gauge(value: number | null, label: string, color: string, max = 100, unit = '%'): EChartsCoreOption {
  return {
    series: [
      {
        type: 'gauge',
        startAngle: 90,
        endAngle: -270,
        min: 0,
        max,
        progress: { show: true, width: 10, itemStyle: { color } },
        axisLine: { lineStyle: { width: 10, color: [[1, '#1f2a3b']] } },
        pointer: { show: false },
        axisTick: { show: false },
        splitLine: { show: false },
        axisLabel: { show: false },
        title: { offsetCenter: [0, '32%'], color: CHART_TEXT, fontSize: 11 },
        detail: {
          offsetCenter: [0, '-8%'],
          fontSize: 20,
          fontWeight: 600,
          color: '#e6ebf2',
          formatter: (v: number) => `${Math.round(v)}${unit}`,
        },
        data: [{ value: value ?? 0, name: label }],
      },
    ],
  };
}

export function donut(data: { name: string; value: number; color: string }[]): EChartsCoreOption {
  return {
    tooltip: { trigger: 'item' },
    series: [
      {
        type: 'pie',
        radius: ['58%', '82%'],
        padAngle: 2,
        label: { show: false },
        data: data.map((d) => ({ name: d.name, value: d.value, itemStyle: { color: d.color } })),
      },
    ],
  };
}
