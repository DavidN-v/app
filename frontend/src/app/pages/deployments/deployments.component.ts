import { DatePipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, DestroyRef, OnInit, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { filter, interval } from 'rxjs';
import { ApiService } from '../../core/api.service';
import { AuthService } from '../../core/auth.service';
import { LiveService } from '../../core/live.service';
import { DeployStage, Deployment, Device, MLModel, PolicyCheck } from '../../core/models';
import { PolicyStore } from '../../core/policy.store';
import { describeError } from '../../shared/errors';
import { SortState } from '../../shared/sort';
import { StatusBadgeComponent } from '../../shared/status-badge.component';
import { ToastService } from '../../shared/toast.service';

export const STEPS: { key: DeployStage; label: string }[] = [
  { key: 'requested', label: 'Solicitado' },
  { key: 'downloading', label: 'Descargando' },
  { key: 'verifying', label: 'Verificando hash' },
  { key: 'installing', label: 'Instalando' },
  { key: 'confirmed', label: 'Confirmado' },
];

/** Estado de cada paso para dibujar la barra de progreso. */
export function stepStates(d: Pick<Deployment, 'status' | 'stage'>): ('done' | 'current' | 'todo' | 'fail')[] {
  if (d.status === 'succeeded') return STEPS.map(() => 'done');
  const reached = Math.max(0, STEPS.findIndex((s) => s.key === d.stage));
  return STEPS.map((_, i) => {
    if (i < reached) return 'done';
    if (i === reached) return d.status === 'failed' ? 'fail' : 'current';
    return d.status === 'failed' ? 'todo' : 'todo';
  });
}

export function elapsed(fromIso: string, toMs: number): string {
  const from = Date.parse(/([zZ]|[+-]\d\d:?\d\d)$/.test(fromIso) ? fromIso : `${fromIso}Z`);
  const s = Math.max(0, Math.round((toMs - from) / 1000));
  return `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`;
}

type DepKey = 'id' | 'model' | 'device' | 'created';

@Component({
  selector: 'eg-deployments',
  imports: [FormsModule, StatusBadgeComponent, DatePipe],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="page-head">
      <div>
        <p class="muted">Cada despliegue pasa por el motor de políticas antes de llegar al dispositivo.</p>
      </div>
    </div>

    @if (auth.can('operator')) {
      <div class="card deploy-form">
        <label>
          Modelo
          <select [ngModel]="modelId()" (ngModelChange)="modelId.set($event); check()">
            <option [ngValue]="null" disabled>Selecciona un modelo</option>
            @for (m of deployable(); track m.id) {
              <option [ngValue]="m.id">{{ m.name }} v{{ m.version }} ({{ m.framework }}) · {{ m.status }}</option>
            }
          </select>
        </label>
        <label>
          Dispositivo
          <select [ngModel]="deviceId()" (ngModelChange)="deviceId.set($event); check()">
            <option [ngValue]="null" disabled>Selecciona un dispositivo</option>
            @for (d of devices(); track d.id) {
              <option [ngValue]="d.id">{{ d.name }} · {{ d.status }}</option>
            }
          </select>
        </label>
        <button class="btn btn-primary" [disabled]="!policy()?.allowed || busy()" (click)="deploy()">
          Desplegar
        </button>

        @if (policy(); as p) {
          <div class="policy-result span-all" [class.ok]="p.allowed">
            @if (p.allowed) {
              <strong>Cumple todas las políticas</strong>
            } @else {
              <strong>Bloqueado por las políticas</strong>
              <ul>
                @for (v of p.violations; track v) {
                  <li>{{ v }}</li>
                }
              </ul>
            }
          </div>
        }
        @if (error()) {
          <p class="form-error span-all">{{ error() }}</p>
        }
      </div>
    }

    <div class="card">
      <div class="table-wrap">
        <table class="table">
          <thead>
            <tr>
              <th [attr.aria-sort]="sort.ariaSort('id')"><button class="th-sort" (click)="sort.toggle('id')"># {{ sort.indicator('id') }}</button></th>
              <th [attr.aria-sort]="sort.ariaSort('model')"><button class="th-sort" (click)="sort.toggle('model')">Modelo {{ sort.indicator('model') }}</button></th>
              <th [attr.aria-sort]="sort.ariaSort('device')"><button class="th-sort" (click)="sort.toggle('device')">Dispositivo {{ sort.indicator('device') }}</button></th>
              <th>Progreso</th>
              <th class="num">Tiempo</th>
              <th>Solicitado por</th>
              <th [attr.aria-sort]="sort.ariaSort('created')"><button class="th-sort" (click)="sort.toggle('created')">Inicio {{ sort.indicator('created') }}</button></th>
              <th>Resultado</th>
              <th>Estado</th>
            </tr>
          </thead>
          <tbody>
            @if (!loaded()) {
              @for (i of skeletonRows; track i) {
                <tr class="skeleton-row"><td colspan="9"><span class="skeleton w-80"></span></td></tr>
              }
            }
            @for (d of sorted(); track d.id) {
              <tr [class.slow]="isSlow(d)">
                <td class="muted tnum">{{ d.id }}</td>
                <td><strong>{{ d.model.name }}</strong><span class="ver muted">v{{ d.model.version }}</span></td>
                <td>{{ d.device_id }}</td>
                <td>
                  <div class="stepper" [attr.aria-label]="'Etapa: ' + stageLabel(d)">
                    @for (s of stepStates(d); track $index) {
                      <i [class]="s" [attr.title]="steps[$index].label"></i>
                    }
                  </div>
                  <span class="step-label" [class.red]="d.status === 'failed'">{{ stageLabel(d) }}</span>
                  @if (isSlow(d)) {
                    <span class="step-warn">Tarda más de lo normal · se cancela a los {{ timeout() }} s</span>
                  }
                </td>
                <td class="num tnum">{{ d.status === 'pending' ? elapsed(d.created_at, now()) : (d.finished_at ? elapsed(d.created_at, parse(d.finished_at)) : '—') }}</td>
                <td>{{ d.requested_by }}</td>
                <td class="muted">{{ d.created_at | date: 'short' }}</td>
                <td class="muted">{{ d.message || '—' }}</td>
                <td><eg-status [status]="d.status" /></td>
              </tr>
            } @empty {
              @if (loaded()) {
                <tr><td colspan="9" class="empty">Aún no hay despliegues. Elige un modelo aprobado y un dispositivo para lanzar el primero.</td></tr>
              }
            }
          </tbody>
        </table>
      </div>
    </div>
  `,
})
export class DeploymentsComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly live = inject(LiveService);
  private readonly toast = inject(ToastService);
  private readonly policies = inject(PolicyStore);
  private readonly destroyRef = inject(DestroyRef);
  protected readonly auth = inject(AuthService);

  protected readonly deployments = signal<Deployment[]>([]);
  private readonly models = signal<MLModel[]>([]);
  protected readonly devices = signal<Device[]>([]);
  protected readonly modelId = signal<number | null>(null);
  protected readonly deviceId = signal<string | null>(null);
  protected readonly policy = signal<PolicyCheck | null>(null);
  protected readonly busy = signal(false);
  protected readonly loaded = signal(false);
  protected readonly skeletonRows = [1, 2, 3, 4];
  protected readonly error = signal('');
  protected readonly now = signal(Date.now());
  protected readonly steps = STEPS;
  protected readonly stepStates = stepStates;
  protected readonly elapsed = elapsed;
  protected readonly sort = new SortState<DepKey>('id');

  protected readonly deployable = computed(() => this.models().filter((m) => m.status !== 'retired'));
  protected readonly timeout = computed(() => {
    const p = this.policies.policies().find((x) => x.key === 'deploy_timeout_s');
    return p ? Number(p.value) : 120;
  });
  protected readonly sorted = computed(() =>
    this.sort.apply(this.deployments(), {
      id: (d) => d.id,
      model: (d) => `${d.model.name} ${d.model.version}`,
      device: (d) => d.device_id,
      created: (d) => d.created_at,
    }),
  );

  ngOnInit(): void {
    this.policies.ensureLoaded();
    this.loadDeployments();
    this.api.models().subscribe((m) => this.models.set(m));
    this.api.devices().subscribe((d) => this.devices.set(this.live.merge(d)));
    // Reloj para el tiempo transcurrido de los despliegues en curso
    interval(1000)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(() => {
        if (this.deployments().some((d) => d.status === 'pending')) this.now.set(Date.now());
      });
    this.live.events$
      .pipe(
        filter((e) => e.type === 'deployment'),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe((e) => {
        if (e.type !== 'deployment') return;
        // Las etapas se aplican al momento; al terminar se recarga para traer el mensaje final
        this.deployments.update((list) =>
          list.map((d) => (d.id === e.data.id ? { ...d, status: e.data.status, stage: e.data.stage ?? d.stage } : d)),
        );
        if (e.data.status !== 'pending') this.loadDeployments();
      });
  }

  protected parse(iso: string): number {
    return Date.parse(/([zZ]|[+-]\d\d:?\d\d)$/.test(iso) ? iso : `${iso}Z`);
  }

  protected isSlow(d: Deployment): boolean {
    return d.status === 'pending' && this.now() - this.parse(d.created_at) > (this.timeout() / 2) * 1000;
  }

  protected stageLabel(d: Deployment): string {
    if (d.status === 'succeeded') return 'Confirmado';
    if (d.status === 'failed') return 'Fallido';
    return STEPS.find((s) => s.key === d.stage)?.label ?? d.stage;
  }

  /** Dry-run contra el motor de políticas cada vez que cambia la selección. */
  check(): void {
    const model = this.modelId();
    const device = this.deviceId();
    this.error.set('');
    if (model === null || device === null) return;
    this.api.checkDeployment(model, device).subscribe((p) => this.policy.set(p));
  }

  deploy(): void {
    const model = this.modelId();
    const device = this.deviceId();
    if (model === null || device === null) return;
    const name = this.models().find((m) => m.id === model);
    this.busy.set(true);
    this.api.deploy(model, device).subscribe({
      next: (dep) => {
        this.busy.set(false);
        this.policy.set(null);
        this.modelId.set(null);
        this.deviceId.set(null);
        this.toast.ok(
          `Despliegue #${dep.id} enviado`,
          `${name ? name.name + ' v' + name.version : 'Modelo'} → ${device.toUpperCase()}. Verás aquí cada etapa.`,
        );
        this.loadDeployments();
      },
      error: (err) => {
        this.busy.set(false);
        const e = describeError(err);
        this.error.set([e.message, ...e.violations].join(' · '));
        this.toast.error('No se pudo desplegar', e.violations[0] ?? e.message);
      },
    });
  }

  private loadDeployments(): void {
    this.api.deployments().subscribe((d) => {
      this.deployments.set(d);
      this.loaded.set(true);
    });
  }
}
