import { ChangeDetectionStrategy, Component, computed, inject, input } from '@angular/core';
import { RouterLink } from '@angular/router';
import { PolicyStore } from '../core/policy.store';

type Metric = 'cpu' | 'ram' | 'temp' | 'latency';
/** Unidad que se muestra detrás de cada métrica. */
const SUFFIX: Record<Metric, string> = { cpu: '%', ram: '%', temp: '°', latency: 'ms' };

/**
 * Muestra el valor de una métrica. Si supera el umbral de su política aparece en rojo,
 * indica el límite al pasar el ratón y enlaza con la página de Políticas para poder
 * consultar o ajustar ese límite.
 */
@Component({
  selector: 'eg-metric',
  imports: [RouterLink],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @if (over()) {
      <a class="metric hot" routerLink="/policies" [attr.data-tip]="tip()" [attr.aria-label]="text() + ', ' + tip()">{{ text() }}</a>
    } @else {
      <span class="metric">{{ text() }}</span>
    }
  `,
})
export class MetricComponent {
  private readonly policy = inject(PolicyStore);
  readonly value = input<number | null>(null);
  readonly metric = input.required<Metric>();
  readonly decimals = input(0);

  protected readonly text = computed(() => {
    const v = this.value();
    return v === null ? '—' : `${v.toFixed(this.decimals())}${SUFFIX[this.metric()]}`;
  });
  protected readonly over = computed(() => this.policy.over(this.metric(), this.value()));
  protected readonly tip = computed(() => this.policy.tip(this.metric(), this.value()));
}
