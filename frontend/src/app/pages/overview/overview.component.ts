import { ChangeDetectionStrategy, Component, DestroyRef, OnInit, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { RouterLink } from '@angular/router';
import { debounceTime, filter, merge, switchMap, timer } from 'rxjs';
import { ApiService } from '../../core/api.service';
import { LiveService } from '../../core/live.service';
import { Alert, Device, Overview } from '../../core/models';
import { ChartDirective } from '../../shared/chart.directive';
import { donut, gauge, latencyChart, sparkline } from '../../shared/charts';
import { STATUS, colorFor, levelColor } from '../../shared/palette';
import { StatusBadgeComponent } from '../../shared/status-badge.component';
import { TimeAgoPipe } from '../../shared/time-ago.pipe';

const REFRESH_MS = 15_000;

function average(values: (number | null)[]): number | null {
  const v = values.filter((x): x is number => x !== null);
  return v.length ? v.reduce((a, b) => a + b, 0) / v.length : null;
}

@Component({
  selector: 'eg-overview',
  imports: [ChartDirective, StatusBadgeComponent, TimeAgoPipe, RouterLink],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './overview.component.html',
})
export class OverviewComponent implements OnInit {
  private readonly api = inject(ApiService);
  protected readonly live = inject(LiveService);
  private readonly destroyRef = inject(DestroyRef);

  protected readonly overview = signal<Overview | null>(null);
  private readonly baseDevices = signal<Device[]>([]);
  protected readonly loaded = signal(false);
  protected readonly skeletonRows = [1, 2, 3, 4];
  private readonly recentAlerts = signal<Alert[]>([]);
  protected readonly colorFor = colorFor;

  protected readonly devices = computed(() => this.live.merge(this.baseDevices()));
  protected readonly online = computed(() => this.devices().filter((d) => d.status === 'online'));
  protected readonly avgLatency = computed(() => average(this.online().map((d) => d.latency_ms)));
  protected readonly avgCpu = computed(() => average(this.online().map((d) => d.cpu)));
  protected readonly avgRam = computed(() => average(this.online().map((d) => d.ram)));
  protected readonly avgTemp = computed(() => average(this.online().map((d) => d.temp)));
  protected readonly offlineText = computed(() => {
    const off = this.devices().length - this.online().length;
    return off === 0 ? 'Toda la flota responde' : `${off} sin conexión`;
  });

  protected fmt(v: number | null): string {
    return v === null ? '—' : v.toFixed(1);
  }

  protected readonly alerts = computed(() => {
    const seen = new Set<number>();
    return [...this.live.alertFeed(), ...this.recentAlerts()]
      .filter((a) => !seen.has(a.id) && seen.add(a.id))
      .slice(0, 4);
  });

  private readonly names = computed(() =>
    Object.fromEntries(this.baseDevices().map((d) => [d.id, d.name])),
  );
  protected readonly latencyOptions = computed(() => latencyChart(this.live.latency(), this.names()));
  // El color de cada indicador solo cambia cuando el valor es preocupante
  protected readonly cpuGauge = computed(() => gauge(this.avgCpu(), 'CPU', levelColor(this.avgCpu(), 75, 90)));
  protected readonly ramGauge = computed(() => gauge(this.avgRam(), 'RAM', levelColor(this.avgRam(), 80, 92)));
  protected readonly tempGauge = computed(() =>
    gauge(this.avgTemp(), 'Temp.', levelColor(this.avgTemp(), 65, 75), 90, '°'),
  );
  protected readonly modelsDonut = computed(() => {
    const s = this.overview()?.models.by_status ?? {};
    return donut([
      { name: 'Desplegados', value: s.deployed ?? 0, color: STATUS.ok },
      { name: 'Aprobados', value: s.approved ?? 0, color: STATUS.accent },
      { name: 'Borradores', value: s.draft ?? 0, color: STATUS.warn },
      { name: 'Retirados', value: s.retired ?? 0, color: STATUS.muted },
    ]);
  });

  protected readonly sparks = computed(() => {
    const latency = this.live.latency();
    return Object.fromEntries(
      this.baseDevices().map((d) => [d.id, sparkline((latency[d.id] ?? []).slice(-60), colorFor(d.id))]),
    );
  });

  ngOnInit(): void {
    // Se refresca cada 15 s y también (agrupado) cuando llega una alerta o un despliegue
    const changes$ = this.live.events$.pipe(
      filter((e) => e.type === 'alert' || e.type === 'deployment'),
      debounceTime(500),
    );
    merge(timer(0, REFRESH_MS), changes$)
      .pipe(
        switchMap(() => this.api.overview()),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe((o) => {
        if (!this.overview()) this.live.seedLatency(o.latency_series);
        this.overview.set(o);
      });
    timer(0, REFRESH_MS)
      .pipe(
        switchMap(() => this.api.devices()),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe((d) => {
        this.baseDevices.set(d);
        this.loaded.set(true);
      });
    this.loadAlerts();
    this.live.events$
      .pipe(
        filter((e) => e.type === 'deployment'),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe(() => this.api.devices().subscribe((d) => this.baseDevices.set(d)));
  }

  private loadAlerts(): void {
    this.api.alerts().subscribe((a) => this.recentAlerts.set(a));
  }
}
