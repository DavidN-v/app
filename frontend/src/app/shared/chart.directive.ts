import { Directive, ElementRef, OnDestroy, afterNextRender, effect, inject, input } from '@angular/core';
import { EChartsCoreOption, echarts } from './echarts';

/** <div [egChart]="options"></div> — gráfica ECharts reactiva a un signal de opciones. */
@Directive({ selector: '[egChart]' })
export class ChartDirective implements OnDestroy {
  readonly egChart = input.required<EChartsCoreOption>();

  private readonly el = inject(ElementRef<HTMLElement>);
  private chart: ReturnType<typeof echarts.init> | null = null;
  private observer: ResizeObserver | null = null;

  constructor() {
    afterNextRender(() => {
      this.chart = echarts.init(this.el.nativeElement, null, { renderer: 'canvas' });
      this.chart.setOption(this.egChart());
      this.observer = new ResizeObserver(() => this.chart?.resize());
      this.observer.observe(this.el.nativeElement);
    });
    effect(() => {
      const options = this.egChart();
      this.chart?.setOption(options, { lazyUpdate: true });
    });
  }

  ngOnDestroy(): void {
    this.observer?.disconnect();
    this.chart?.dispose();
  }
}
