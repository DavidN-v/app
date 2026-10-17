import { ChangeDetectionStrategy, Component, OnInit, computed, inject, input, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { ApiService } from '../../core/api.service';
import { AuthService } from '../../core/auth.service';
import { LiveService } from '../../core/live.service';
import { Device } from '../../core/models';
import { MetricComponent } from '../../shared/metric.component';
import { describeError } from '../../shared/errors';
import { colorFor } from '../../shared/palette';
import { SortState } from '../../shared/sort';
import { StatusBadgeComponent } from '../../shared/status-badge.component';
import { TimeAgoPipe } from '../../shared/time-ago.pipe';
import { ToastService, UNDO_WINDOW_MS } from '../../shared/toast.service';

const KIND_LABEL: Record<Device['kind'], string> = {
  rpi5: 'Raspberry Pi 5',
  arduino: 'Arduino',
  esp32: 'ESP32',
};

@Component({
  selector: 'eg-devices',
  imports: [StatusBadgeComponent, TimeAgoPipe, MetricComponent, ReactiveFormsModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="page-head">
      <div>
        <p class="muted">Inventario de la flota edge con su estado en vivo.</p>
      </div>
      <input class="search" type="search" aria-label="Buscar dispositivos" placeholder="Buscar por nombre, función o tipo" (input)="query.set($any($event.target).value)" />
      @if (auth.can('admin')) {
        <button class="btn btn-primary" (click)="showForm.set(!showForm())">{{ showForm() ? 'Cerrar' : 'Dar de alta' }}</button>
      }
    </div>
    @if (showForm()) {
      <form class="card form-grid" [formGroup]="form" (ngSubmit)="register()">
        <label>
          Identificador
          <input formControlName="id" class="mono" placeholder="rpi5-taller" />
          @if (form.controls.id.touched && form.controls.id.invalid) {
            <small class="form-error">Minúsculas, números y guiones (2 a 64 caracteres). Debe coincidir con EDGE_DEVICE_ID del dispositivo.</small>
          }
        </label>
        <label>Nombre<input formControlName="name" placeholder="Raspberry Pi 5 (Taller)" /></label>
        <label>
          Hardware
          <select formControlName="kind">
            <option value="rpi5">Raspberry Pi 5</option>
            <option value="arduino">Arduino</option>
            <option value="esp32">ESP32</option>
          </select>
        </label>
        <label>Función<input formControlName="role" placeholder="Visión artificial" /></label>
        <label class="span-2">Ubicación<input formControlName="location" placeholder="Laboratorio" /></label>
        <div class="span-2 form-actions">
          <button class="btn btn-primary" type="submit" [disabled]="form.invalid || busy()">Dar de alta</button>
        </div>
      </form>
    }
    <div class="card">
      <div class="table-wrap">
        <table class="table">
          <thead>
            <tr>
              <th [attr.aria-sort]="sort.ariaSort('name')"><button class="th-sort" (click)="sort.toggle('name')">Dispositivo {{ sort.indicator('name') }}</button></th>
              <th>Hardware</th><th>Función</th><th>Modelo activo</th>
              <th class="num" [attr.aria-sort]="sort.ariaSort('cpu')"><button class="th-sort" (click)="sort.toggle('cpu')">CPU {{ sort.indicator('cpu') }}</button></th>
              <th class="num" [attr.aria-sort]="sort.ariaSort('ram')"><button class="th-sort" (click)="sort.toggle('ram')">RAM {{ sort.indicator('ram') }}</button></th>
              <th class="num" [attr.aria-sort]="sort.ariaSort('temp')"><button class="th-sort" (click)="sort.toggle('temp')">Temp. {{ sort.indicator('temp') }}</button></th>
              <th class="num" [attr.aria-sort]="sort.ariaSort('latency')"><button class="th-sort" (click)="sort.toggle('latency')">Latencia {{ sort.indicator('latency') }}</button></th>
              <th>Último dato</th>
              <th [attr.aria-sort]="sort.ariaSort('status')"><button class="th-sort" (click)="sort.toggle('status')">Estado {{ sort.indicator('status') }}</button></th>
              @if (auth.can('admin')) { <th><span class="sr-only">Acciones</span></th> }
            </tr>
          </thead>
          <tbody>
            @if (!loaded()) {
            @for (i of skeletonRows; track i) {
              <tr class="skeleton-row"><td colspan="10"><span class="skeleton w-80"></span></td></tr>
            }
          }
            @for (d of filtered(); track d.id) {
              <tr [class.focused]="focus() === d.id" [attr.id]="'unit-' + d.id">
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
                <td class="num"><eg-metric metric="cpu" [value]="d.cpu" /></td>
                <td class="num"><eg-metric metric="ram" [value]="d.ram" /></td>
                <td class="num"><eg-metric metric="temp" [value]="d.temp" /></td>
                <td class="num"><eg-metric metric="latency" [value]="d.latency_ms" /></td>
                <td class="muted">{{ d.last_seen | timeAgo }}</td>
                <td><eg-status [status]="d.status" /></td>
                @if (auth.can('admin')) {
                  <td><button class="btn btn-ghost btn-sm" [disabled]="removing().has(d.id)" (click)="decommission(d)">Dar de baja</button></td>
                }
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
  private readonly toast = inject(ToastService);
  private readonly undoWindow = inject(UNDO_WINDOW_MS);
  protected readonly auth = inject(AuthService);
  private readonly base = signal<Device[]>([]);
  readonly focus = input<string | undefined>();
  protected readonly sort = new SortState<'name' | 'cpu' | 'ram' | 'temp' | 'latency' | 'status'>();
  protected readonly query = signal('');
  protected readonly loaded = signal(false);
  protected readonly skeletonRows = [1, 2, 3, 4, 5];
  protected readonly kindLabel = KIND_LABEL;
  protected readonly colorFor = colorFor;
  protected readonly showForm = signal(false);
  protected readonly busy = signal(false);
  protected readonly removing = signal<ReadonlySet<string>>(new Set());

  protected readonly form = inject(FormBuilder).nonNullable.group({
    // Mismo formato que exige la API: se usa como parte de los temas MQTT
    id: ['', [Validators.required, Validators.pattern(/^[a-z0-9][a-z0-9-]{1,63}$/)]],
    name: ['', Validators.required],
    kind: ['rpi5' as Device['kind'], Validators.required],
    role: [''],
    location: [''],
  });

  protected readonly filtered = computed(() => {
    const q = this.query().trim().toLowerCase();
    const devices = this.live.merge(this.base());
    const list = q
      ? devices.filter((d) => [d.id, d.name, d.role, d.kind].some((f) => f.toLowerCase().includes(q)))
      : devices;
    return this.sort.apply(list, {
      name: (d) => d.name,
      cpu: (d) => d.cpu,
      ram: (d) => d.ram,
      temp: (d) => d.temp,
      latency: (d) => d.latency_ms,
      status: (d) => d.status,
    });
  });

  ngOnInit(): void {
    this.api.devices().subscribe((d) => {
      this.base.set(d);
      this.loaded.set(true);
      const focus = this.focus();
      if (focus) setTimeout(() => document.getElementById('unit-' + focus)?.scrollIntoView({ block: 'center', behavior: 'smooth' }));
    });
  }

  register(): void {
    this.busy.set(true);
    this.api.registerDevice(this.form.getRawValue()).subscribe({
      next: (device) => {
        this.base.update((list) => [...list, device]);
        this.busy.set(false);
        this.showForm.set(false);
        this.form.reset();
        this.toast.ok(`${device.name} dado de alta`, `Aparecerá en línea en cuanto el dispositivo se conecte como ${device.id}.`);
      },
      error: (err) => {
        this.busy.set(false);
        const { message, violations } = describeError(err);
        this.toast.error('No se pudo dar de alta', [message, ...violations].join(' · '));
      },
    });
  }

  decommission(d: Device): void {
    const mark = (on: boolean) =>
      this.removing.update((s) => {
        const next = new Set(s);
        if (on) next.add(d.id);
        else next.delete(d.id);
        return next;
      });
    mark(true);
    this.toast.withUndo(
      `Baja de ${d.name}`,
      () =>
        this.api.decommissionDevice(d.id).subscribe({
          next: () => {
            this.base.update((list) => list.filter((x) => x.id !== d.id));
            mark(false);
            this.toast.ok(`${d.name} dado de baja`, 'Sus mensajes se descartarán a partir de ahora.');
          },
          error: (err) => {
            mark(false);
            this.toast.error('No se pudo dar de baja', describeError(err).message);
          },
        }),
      { detail: 'Dejará de aceptarse cualquier mensaje suyo.', windowMs: this.undoWindow, onUndo: () => mark(false) },
    );
  }

  protected fmt(v: number | null, unit: string): string {
    return v === null ? '—' : `${v.toFixed(0)}${unit}`;
  }
}
