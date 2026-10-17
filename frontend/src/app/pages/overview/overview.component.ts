import { ChangeDetectionStrategy, Component, DestroyRef, OnInit, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { Router, RouterLink } from '@angular/router';
import { debounceTime, filter, groupBy, merge, mergeMap, partition, switchMap, throttleTime, timer } from 'rxjs';
import { ApiService } from '../../core/api.service';
import { LiveService } from '../../core/live.service';
import { Alert, Device, LatencyWindow, LiveEvent, Overview, Point } from '../../core/models';
import { PolicyStore } from '../../core/policy.store';
import { ChartDirective } from '../../shared/chart.directive';
import { latencyChart, sparkline } from '../../shared/charts';
import { MetricComponent } from '../../shared/metric.component';
import { CountUpDirective } from '../../shared/count-up.directive';
import { colorFor } from '../../shared/palette';
import { SortState } from '../../shared/sort';
import { StatusBadgeComponent } from '../../shared/status-badge.component';
import { TimeAgoPipe } from '../../shared/time-ago.pipe';

const REFRESH_MS = 15_000;
const HISTORY_REFRESH_MS = 60_000;
const LOG_LINES = 18;
const SEGMENTS = 20;
const RANGE_KEY = 'eg.latency.window';
const WINDOW_SECONDS: Record<LatencyWindow, number> = { '5m': 300, '1h': 3600, '24h': 86400 };

export type LogKind = 'TEL' | 'INF' | 'ALR' | 'LNK' | 'OTA';
export const LOG_KINDS: LogKind[] = ['TEL', 'INF', 'ALR', 'LNK', 'OTA'];

export interface LogLine {
  id: number;
  time: string;
  who: string;
  /** Dispositivo al que lleva el clic, si lo hay */
  device: string | null;
  kind: LogKind;
  msg: string;
  hot: boolean;
}

type FleetKey = 'id' | 'cpu' | 'ram' | 'temp' | 'latency';

function average(values: (number | null)[]): number | null {
  const v = values.filter((x): x is number => x !== null);
  return v.length ? v.reduce((a, b) => a + b, 0) / v.length : null;
}

/** Convierte un evento del WebSocket en una línea del registro en vivo. */
export function toLogLine(e: LiveEvent, id: number, now = new Date()): LogLine | null {
  const time = now.toISOString().slice(11, 23);
  switch (e.type) {
    case 'telemetry':
      return {
        id, time, who: e.data.id, device: e.data.id, kind: 'TEL', hot: (e.data.temp ?? 0) > 75,
        msg: `cpu ${e.data.cpu.toFixed(0)}% ram ${e.data.ram.toFixed(0)}% t ${e.data.temp?.toFixed(1) ?? '—'}°`,
      };
    case 'inference':
      return {
        id, time, who: e.data.id, device: e.data.id, kind: 'INF', hot: e.data.latency_ms > 100,
        msg: `${e.data.model} ${e.data.latency_ms.toFixed(1)}ms${e.data.confidence !== null ? ` conf ${e.data.confidence.toFixed(2)}` : ''}`,
      };
    case 'alert':
      return { id, time, who: e.data.device_id ?? 'sistema', device: e.data.device_id, kind: 'ALR', hot: true, msg: e.data.message };
    case 'device_status':
      return {
        id, time, who: e.data.id, device: e.data.id, kind: 'LNK', hot: e.data.status === 'offline',
        msg: e.data.status === 'online' ? 'enlace establecido' : 'enlace perdido',
      };
    case 'deployment':
      return {
        id, time, who: `dep-${e.data.id}`, device: null, kind: 'OTA', hot: e.data.status === 'failed',
        msg: `despliegue ${e.data.stage ?? e.data.status}`,
      };
    default:
      return null;
  }
}

/** Filtro del registro en vivo por tipo y dispositivo. */
export function logMatches(line: LogLine, kinds: ReadonlySet<LogKind>, device: string | null): boolean {
  return kinds.has(line.kind) && (!device || line.device === device);
}

function readWindow(): LatencyWindow {
  try {
    const v = localStorage.getItem(RANGE_KEY);
    return v === '1h' || v === '24h' ? v : '5m';
  } catch {
    return '5m';
  }
}

@Component({
  selector: 'eg-overview',
  imports: [ChartDirective, CountUpDirective, StatusBadgeComponent, TimeAgoPipe, RouterLink, MetricComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './overview.component.html',
})
export class OverviewComponent implements OnInit {
  private readonly api = inject(ApiService);
  protected readonly live = inject(LiveService);
  protected readonly policy = inject(PolicyStore);
  private readonly router = inject(Router);
  private readonly destroyRef = inject(DestroyRef);

  protected readonly overview = signal<Overview | null>(null);
  private readonly baseDevices = signal<Device[]>([]);
  private readonly recentAlerts = signal<Alert[]>([]);
  protected readonly loaded = signal(false);
  protected readonly skeletonRows = [1, 2, 3, 4, 5, 6];
  protected readonly colorFor = colorFor;

  // --- Registro en vivo ---------------------------------------------------
  private readonly allLog = signal<LogLine[]>([]);
  protected readonly paused = signal(false);
  private readonly hoverPaused = signal(false);
  private readonly frozen = signal<LogLine[] | null>(null);
  protected readonly logKinds = signal<ReadonlySet<LogKind>>(new Set(LOG_KINDS));
  protected readonly logDevice = signal<string | null>(null);
  protected readonly kindsList = LOG_KINDS;
  private logId = 0;
  protected readonly isPaused = computed(() => this.paused() || this.hoverPaused());
  protected readonly log = computed(() => {
    const source = this.frozen() ?? this.allLog();
    return source.filter((l) => logMatches(l, this.logKinds(), this.logDevice())).slice(0, LOG_LINES);
  });
  protected readonly pendingLines = computed(() => {
    const f = this.frozen();
    if (!f) return 0;
    const newest = f[0]?.id ?? 0;
    return this.allLog().filter((l) => l.id > newest && logMatches(l, this.logKinds(), this.logDevice())).length;
  });

  // --- Gráfica --------------------------------------------------------------
  protected readonly window = signal<LatencyWindow>(readWindow());
  protected readonly windows: { key: LatencyWindow; label: string }[] = [
    { key: '5m', label: '5 min' },
    { key: '1h', label: '1 h' },
    { key: '24h', label: '24 h' },
  ];
  private readonly history = signal<Record<string, Point[]>>({});
  protected readonly hiddenSeries = signal<ReadonlySet<string>>(new Set());
  protected readonly isolated = signal<string | null>(null);

  // --- Tabla ------------------------------------------------------------------
  protected readonly fleetSort = new SortState<FleetKey>();

  protected readonly devices = computed(() => this.live.merge(this.baseDevices()));
  protected readonly sortedDevices = computed(() =>
    this.fleetSort.apply(this.devices(), {
      id: (d) => d.id,
      cpu: (d) => d.cpu,
      ram: (d) => d.ram,
      temp: (d) => d.temp,
      latency: (d) => d.latency_ms,
    }),
  );
  protected readonly online = computed(() => this.devices().filter((d) => d.status === 'online'));
  protected readonly avgLatency = computed(() => average(this.online().map((d) => d.latency_ms)));
  protected readonly avgCpu = computed(() => average(this.online().map((d) => d.cpu)));
  protected readonly avgRam = computed(() => average(this.online().map((d) => d.ram)));
  protected readonly offlineText = computed(() => {
    const off = this.devices().length - this.online().length;
    return off === 0 ? 'Flota completa' : `${off} sin enlace`;
  });

  protected readonly status = computed(() => {
    const s = this.overview()?.models.by_status ?? {};
    return { deployed: s.deployed ?? 0, approved: s.approved ?? 0, draft: s.draft ?? 0, retired: s.retired ?? 0 };
  });

  /** Solo alertas abiertas: las que el sistema ya resolvió (p. ej. una unidad que volvió) no se muestran. */
  protected readonly alerts = computed(() => this.recentAlerts().filter((a) => a.status !== 'resolved').slice(0, 4));

  private readonly names = computed(() =>
    Object.fromEntries(this.baseDevices().map((d) => [d.id, d.id.toUpperCase()])),
  );

  /** 5 min usa los puntos en vivo; 1 h y 24 h el historial agregado del servidor. */
  private readonly chartSeries = computed<Record<string, Point[]>>(() => {
    if (this.window() !== '5m') return this.history();
    const since = Date.now() / 1000 - WINDOW_SECONDS['5m'];
    const live = this.live.latency();
    return Object.fromEntries(Object.entries(live).map(([k, v]) => [k, v.filter(([t]) => t >= since)]));
  });

  protected readonly latencyOptions = computed(() =>
    latencyChart(this.chartSeries(), this.names(), {
      hidden: this.hiddenSeries(),
      threshold: this.policy.thresholds().latency.value,
    }),
  );
  protected readonly sparks = computed(() => {
    const latency = this.live.latency();
    return Object.fromEntries(
      this.baseDevices().map((d) => [d.id, sparkline((latency[d.id] ?? []).slice(-60), colorFor(d.id))]),
    );
  });

  protected segmentsFor(pct: number | null): boolean[] {
    const lit = Math.round(((pct ?? 0) / 100) * SEGMENTS);
    return Array.from({ length: SEGMENTS }, (_, i) => i < lit);
  }

  protected pct(v: number | null): string {
    return v === null ? '—' : `${v.toFixed(0)}%`;
  }

  // --- Acciones de la gráfica ------------------------------------------------
  protected setWindow(w: LatencyWindow): void {
    if (this.window() === w) return;
    this.window.set(w);
    try {
      localStorage.setItem(RANGE_KEY, w);
    } catch {
      /* sin almacenamiento: el rango dura la sesión */
    }
    this.loadHistory();
  }

  /** Clic en una fila o en una tarjeta: deja solo ese dispositivo en la gráfica (otro clic lo deshace). */
  protected isolate(id: string): void {
    const name = id.toUpperCase();
    if (this.isolated() === id) {
      this.isolated.set(null);
      this.hiddenSeries.set(new Set());
      return;
    }
    this.isolated.set(id);
    this.hiddenSeries.set(new Set(Object.values(this.names()).filter((n) => n !== name)));
  }

  protected onLegend(e: { selected: Record<string, boolean> }): void {
    const hidden = new Set(Object.entries(e.selected).filter(([, on]) => !on).map(([n]) => n));
    this.hiddenSeries.set(hidden);
    const visible = Object.values(this.names()).filter((n) => !hidden.has(n));
    this.isolated.set(visible.length === 1 ? visible[0].toLowerCase() : null);
  }

  protected showAll(): void {
    this.isolated.set(null);
    this.hiddenSeries.set(new Set());
  }

  // --- Acciones del registro ------------------------------------------------
  protected setHover(on: boolean): void {
    this.hoverPaused.set(on);
    this.syncFreeze();
  }

  protected togglePause(): void {
    this.paused.update((p) => !p);
    this.syncFreeze();
  }

  protected toggleKind(kind: LogKind): void {
    this.logKinds.update((set) => {
      const next = new Set(set);
      if (next.has(kind)) {
        if (next.size > 1) next.delete(kind);
      } else {
        next.add(kind);
      }
      return next;
    });
  }

  protected setLogDevice(value: string): void {
    this.logDevice.set(value || null);
  }

  protected openDevice(line: LogLine): void {
    if (line.device) void this.router.navigate(['/devices'], { queryParams: { focus: line.device } });
  }

  private syncFreeze(): void {
    if (this.isPaused()) {
      if (!this.frozen()) this.frozen.set(this.allLog());
    } else {
      this.frozen.set(null);
    }
  }

  private loadHistory(): void {
    this.api.latencyHistory(this.window()).subscribe((h) => {
      if (h.window === '5m') this.live.seedLatency(h.series);
      else if (h.window === this.window()) this.history.set(h.series);
    });
  }

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
        this.overview.set(o);
        this.api.alerts().subscribe((a) => this.recentAlerts.set(a));
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

    // Historial de la gráfica: al entrar (sobrevive a recargas) y cada minuto en 1 h / 24 h
    this.loadHistory();
    timer(HISTORY_REFRESH_MS, HISTORY_REFRESH_MS)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(() => {
        if (this.window() !== '5m') this.loadHistory();
      });

    // Registro en vivo: los eventos importantes entran siempre; la telemetría y las inferencias,
    // a ritmo legible y repartido por dispositivo (si no, el más rápido acapara el registro)
    const [important$, chatter$] = partition(
      this.live.events$.pipe(filter((e) => e.type !== 'ping')),
      (e) => e.type !== 'telemetry' && e.type !== 'inference',
    );
    const perDevice$ = chatter$.pipe(
      groupBy((e) => (e.type === 'telemetry' || e.type === 'inference' ? `${e.type}:${e.data.id}` : '')),
      mergeMap((group$) => group$.pipe(throttleTime(1500))),
    );
    merge(important$, perDevice$)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe((e) => {
        const line = toLogLine(e, ++this.logId);
        if (line) this.allLog.update((l) => [line, ...l].slice(0, 200));
      });
    this.live.events$
      .pipe(
        filter((e) => e.type === 'deployment' && e.data.status !== 'pending'),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe(() => this.api.devices().subscribe((d) => this.baseDevices.set(d)));
  }
}
