import { DatePipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, DestroyRef, OnInit, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { filter } from 'rxjs';
import { ApiService } from '../../core/api.service';
import { AuthService } from '../../core/auth.service';
import { LiveService } from '../../core/live.service';
import { Alert } from '../../core/models';
import { StatusBadgeComponent } from '../../shared/status-badge.component';

type Filter = Alert['status'] | 'active' | 'all';

const KIND_LABELS: Record<string, string> = {
  high_temperature: 'Temperatura',
  high_cpu: 'CPU',
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
    <div class="tabs">
      @for (f of filters; track f.key) {
        <button class="tab" [class.active]="filter() === f.key" (click)="filter.set(f.key)">{{ f.label }}</button>
      }
    </div>
    <div class="card">
      <div class="table-wrap">
        <table class="table">
          <thead>
            <tr><th>Severidad</th><th>Mensaje</th><th>Tipo</th><th>Dispositivo</th><th>Fecha</th><th>Estado</th><th></th></tr>
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
                <tr><td colspan="7" class="empty">No hay alertas en esta vista.</td></tr>
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
    const all = this.alerts();
    if (f === 'all') return all;
    if (f === 'active') return all.filter((a) => a.status !== 'resolved');
    return all.filter((a) => a.status === f);
  });

  ngOnInit(): void {
    this.load();
    this.live.events$
      .pipe(
        filter((e) => e.type === 'alert'),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe(() => this.load());
  }

  act(alert: Alert, status: 'acknowledged' | 'resolved'): void {
    this.api.actOnAlert(alert.id, status).subscribe((updated) =>
      this.alerts.update((list) => list.map((a) => (a.id === updated.id ? updated : a))),
    );
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
