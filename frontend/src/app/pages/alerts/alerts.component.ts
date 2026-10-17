import { DatePipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, DestroyRef, OnInit, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { filter } from 'rxjs';
import { ApiService } from '../../core/api.service';
import { AuthService } from '../../core/auth.service';
import { LiveService } from '../../core/live.service';
import { Alert } from '../../core/models';
import { describeError } from '../../shared/errors';
import { SortState, matchesQuery } from '../../shared/sort';
import { StatusBadgeComponent } from '../../shared/status-badge.component';
import { ToastService } from '../../shared/toast.service';
import { NotifyService } from '../../core/notify.service';

type Filter = Alert['status'] | 'active' | 'all';
type AlertKey = 'severity' | 'kind' | 'device' | 'created' | 'status';
const SEV_RANK: Record<string, number> = { critical: 3, warning: 2, info: 1 };

const KIND_LABELS: Record<string, string> = {
  high_temperature: 'Temperatura',
  high_cpu: 'CPU',
  high_ram: 'RAM',
  high_latency: 'Latencia',
  drift: 'Drift',
  offline: 'Conexión',
  deployment_failed: 'Despliegue',
  unregistered_device: 'Dispositivo no registrado',
};

@Component({
  selector: 'eg-alerts',
  imports: [StatusBadgeComponent, DatePipe],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="page-head">
      <div>
        <p class="muted">Generadas por las políticas de temperatura, CPU, latencia, drift, conectividad y despliegue.</p>
      </div>
    </div>
    <div class="toolbar">
      <div class="tabs">
        @for (f of filters; track f.key) {
          <button class="tab" [class.active]="filter() === f.key" (click)="filter.set(f.key)">{{ f.label }}</button>
        }
      </div>
      <input class="search" type="search" placeholder="Buscar mensaje, tipo o unidad…" aria-label="Buscar alertas"
        [value]="query()" (input)="query.set($any($event.target).value)" />
    </div>
    <div class="card">
      <div class="table-wrap">
        <table class="table">
          <thead>
            <tr>
              <th [attr.aria-sort]="sort.ariaSort('severity')"><button class="th-sort" (click)="sort.toggle('severity')">Severidad {{ sort.indicator('severity') }}</button></th>
              <th>Mensaje</th>
              <th [attr.aria-sort]="sort.ariaSort('kind')"><button class="th-sort" (click)="sort.toggle('kind')">Tipo {{ sort.indicator('kind') }}</button></th>
              <th [attr.aria-sort]="sort.ariaSort('device')"><button class="th-sort" (click)="sort.toggle('device')">Dispositivo {{ sort.indicator('device') }}</button></th>
              <th [attr.aria-sort]="sort.ariaSort('created')"><button class="th-sort" (click)="sort.toggle('created')">Fecha {{ sort.indicator('created') }}</button></th>
              <th [attr.aria-sort]="sort.ariaSort('status')"><button class="th-sort" (click)="sort.toggle('status')">Estado {{ sort.indicator('status') }}</button></th>
              <th></th>
            </tr>
          </thead>
          <tbody>
          @if (!loaded()) {
            @for (i of skeletonRows; track i) {
              <tr class="skeleton-row"><td colspan="7"><span class="skeleton w-80"></span></td></tr>
            }
          }
            @for (a of visible(); track a.id) {
              <tr>
                <td><eg-status [status]="a.severity" /></td>
                <td>{{ a.message }}</td>
                <td class="muted">{{ kindLabel(a.kind) }}</td>
                <td>{{ a.device_id ?? '—' }}</td>
                <td class="muted">{{ a.created_at | date: 'short' }}</td>
                <td>
                  <eg-status [status]="a.status" />
                  @if (a.handled_by) { <div class="muted small">{{ a.handled_by }}</div> }
                </td>
                <td class="actions">
                  @if (auth.can('operator')) {
                    @if (a.status === 'open') {
                      <button class="btn btn-sm btn-ghost" (click)="act(a, 'acknowledged')">Reconocer</button>
                    }
                    @if (a.status !== 'resolved') {
                      <button class="btn btn-sm btn-success" (click)="act(a, 'resolved')">Resolver</button>
                    }
                  }
                </td>
              </tr>
            } @empty {
              @if (loaded()) {
                <tr><td colspan="7" class="empty">{{ query() ? 'Ninguna alerta coincide con la búsqueda' : 'No hay alertas en esta vista' }}</td></tr>
              }
            }
          </tbody>
        </table>
      </div>
    </div>
  `,
})
export class AlertsComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly live = inject(LiveService);
  private readonly destroyRef = inject(DestroyRef);
  protected readonly auth = inject(AuthService);
  private readonly toast = inject(ToastService);
  private readonly notify = inject(NotifyService);
  protected readonly query = signal('');
  protected readonly sort = new SortState<AlertKey>('created');

  protected readonly alerts = signal<Alert[]>([]);
  protected readonly filter = signal<Filter>('active');
  protected readonly loaded = signal(false);
  protected readonly skeletonRows = [1, 2, 3, 4, 5];
  protected readonly filters: { key: Filter; label: string }[] = [
    { key: 'active', label: 'Activas' },
    { key: 'open', label: 'Abiertas' },
    { key: 'acknowledged', label: 'Reconocidas' },
    { key: 'resolved', label: 'Resueltas' },
    { key: 'all', label: 'Todas' },
  ];

  protected readonly visible = computed(() => {
    const f = this.filter();
    const q = this.query();
    const list = this.alerts().filter((a) => {
      const byStatus = f === 'all' || (f === 'active' ? a.status !== 'resolved' : a.status === f);
      return byStatus && matchesQuery(q, a.message, a.kind, this.kindLabel(a.kind), a.device_id);
    });
    return this.sort.apply(list, {
      severity: (a) => SEV_RANK[a.severity] ?? 0,
      kind: (a) => this.kindLabel(a.kind),
      device: (a) => a.device_id,
      created: (a) => a.created_at,
      status: (a) => a.status,
    });
  });

  ngOnInit(): void {
    this.load();
    this.live.events$
      .pipe(
        filter((e) => e.type === 'alert' || e.type === 'alert_resolved'),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe(() => this.load());
  }

  act(alert: Alert, status: 'acknowledged' | 'resolved'): void {
    this.api.actOnAlert(alert.id, status).subscribe({
      next: (updated) => {
        this.alerts.update((list) => list.map((a) => (a.id === updated.id ? updated : a)));
        this.toast.ok(status === 'resolved' ? 'Alerta resuelta' : 'Alerta reconocida', alert.message);
        this.notify.refreshCount();
      },
      error: (err) => this.toast.error('No se pudo actualizar la alerta', describeError(err).message),
    });
  }

  protected kindLabel(kind: string): string {
    return KIND_LABELS[kind] ?? kind;
  }

  private load(): void {
    this.api.alerts().subscribe((a) => {
      this.alerts.set(a);
      this.loaded.set(true);
    });
  }
}
