import { ChangeDetectionStrategy, Component, computed, inject, input } from '@angular/core';
import { RouterLink } from '@angular/router';
import { PolicyStore } from '../core/policy.store';

type Metric = 'cpu' | 'ram' | 'temp' | 'latency';
const SUFFIX: Record<Metric, string> = { cpu: '%', ram: '%', temp: '°', latency: 'ms' };

/**
 * Cifra con umbral: en rojo si supera la política, con el límite al pasar el ratón
 * y un enlace a Políticas para entender (o ajustar) por qué está en rojo.
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
