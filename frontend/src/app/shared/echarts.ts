// Registro de ECharts por partes: solo se incluyen en la aplicación los tipos de gráfica y
// componentes que se usan, lo que reduce mucho el tamaño de la descarga.
import { GaugeChart, LineChart, PieChart } from 'echarts/charts';
import {
  GridComponent,
  LegendComponent,
  TooltipComponent,
  DataZoomComponent,
} from 'echarts/components';
import * as echarts from 'echarts/core';
import { CanvasRenderer } from 'echarts/renderers';

echarts.use([
  LineChart,
  GaugeChart,
  PieChart,
  GridComponent,
  LegendComponent,
  TooltipComponent,
  DataZoomComponent,
  CanvasRenderer,
]);

export { echarts };
export type { EChartsCoreOption } from 'echarts/core';
