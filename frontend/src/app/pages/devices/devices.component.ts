import { ChangeDetectionStrategy, Component, OnInit, computed, inject, signal } from '@angular/core';
import { ApiService } from '../../core/api.service';
import { LiveService } from '../../core/live.service';
import { Device } from '../../core/models';
import { colorFor } from '../../shared/palette';
import { StatusBadgeComponent } from '../../shared/status-badge.component';
import { TimeAgoPipe } from '../../shared/time-ago.pipe';

const KIND_LABEL: Record<Device['kind'], string> = {
  rpi5: 'Raspberry Pi 5',
  arduino: 'Arduino',
  esp32: 'ESP32',
};

@Component({
  selector: 'eg-devices',
  imports: [StatusBadgeComponent, TimeAgoPipe],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="page-head">
      <div>
        <p class="muted">Inventario de la flota edge con su estado en vivo.</p>
      </div>
      <input class="search" type="search" aria-label="Buscar dispositivos" placeholder="Buscar por nombre, función o tipo" (input)="query.set($any($event.target).value)" />
    </div>
    <div class="card">
      <div class="table-wrap">
        <table class="table">
          <thead>
            <tr>
              <th>Dispositivo</th><th>Hardware</th><th>Función</th><th>Modelo activo</th>
              <th class="num">CPU</th><th class="num">RAM</th><th class="num">Temp.</th>
              <th class="num">Latencia</th><th>Último dato</th><th>Estado</th>
            </tr>
          </thead>
          <tbody>
            @if (!loaded()) {
            @for (i of skeletonRows; track i) {
              <tr class="skeleton-row"><td colspan="10"><span class="skeleton w-80"></span></td></tr>
            }
          }
            @for (d of filtered(); track d.id) {
              <tr>
                <td>
                  <span class="swatch" [style.background]="colorFor(d.id)"></span>
                  <strong>{{ d.name }}</strong>
                  <div class="muted small">{{ d.id }}</div>
                </td>
                <td>{{ kindLabel[d.kind] }}</td>
                <td class="muted">{{ d.role }}</td>
                <td>
                  {{ d.current_model ? d.current_model.name + ' v' + d.current_model.version : '—' }}
                </td>
                <td class="num">{{ fmt(d.cpu, '%') }}</td>
                <td class="num">{{ fmt(d.ram, '%') }}</td>
                <td class="num" [class.red]="(d.temp ?? 0) > 75">{{ fmt(d.temp, ' °C') }}</td>
                <td class="num">{{ fmt(d.latency_ms, ' ms') }}</td>
                <td class="muted">{{ d.last_seen | timeAgo }}</td>
                <td><eg-status [status]="d.status" /></td>
              </tr>
            } @empty {
              @if (loaded()) {
                <tr><td colspan="10" class="empty">{{ query() ? 'Ningún dispositivo coincide con la búsqueda.' : 'Aún no hay dispositivos registrados.' }}</td></tr>
              }
            }
          </tbody>
        </table>
      </div>
    </div>
  `,
})
export class DevicesComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly live = inject(LiveService);
  private readonly base = signal<Device[]>([]);
  protected readonly query = signal('');
  protected readonly loaded = signal(false);
  protected readonly skeletonRows = [1, 2, 3, 4, 5];
  protected readonly kindLabel = KIND_LABEL;
  protected readonly colorFor = colorFor;

  protected readonly filtered = computed(() => {
    const q = this.query().trim().toLowerCase();
    const devices = this.live.merge(this.base());
    return q
      ? devices.filter((d) => [d.id, d.name, d.role, d.kind].some((f) => f.toLowerCase().includes(q)))
      : devices;
  });

  ngOnInit(): void {
    this.api.devices().subscribe((d) => {
      this.base.set(d);
      this.loaded.set(true);
    });
  }

  protected fmt(v: number | null, unit: string): string {
    return v === null ? '—' : `${v.toFixed(0)}${unit}`;
  }
}
