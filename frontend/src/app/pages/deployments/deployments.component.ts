import { DatePipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, DestroyRef, OnInit, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { filter } from 'rxjs';
import { ApiService } from '../../core/api.service';
import { AuthService } from '../../core/auth.service';
import { LiveService } from '../../core/live.service';
import { Deployment, Device, MLModel, PolicyCheck } from '../../core/models';
import { describeError } from '../../shared/errors';
import { StatusBadgeComponent } from '../../shared/status-badge.component';

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
            <tr><th>#</th><th>Modelo</th><th>Dispositivo</th><th>Solicitado por</th><th>Inicio</th><th>Fin</th><th>Resultado</th><th>Estado</th></tr>
          </thead>
          <tbody>
          @if (!loaded()) {
            @for (i of skeletonRows; track i) {
              <tr class="skeleton-row"><td colspan="8"><span class="skeleton w-80"></span></td></tr>
            }
          }
            @for (d of deployments(); track d.id) {
              <tr>
                <td class="muted tnum">{{ d.id }}</td>
                <td><strong>{{ d.model.name }}</strong><span class="ver muted">v{{ d.model.version }}</span></td>
                <td>{{ d.device_id }}</td>
                <td>{{ d.requested_by }}</td>
                <td class="muted">{{ d.created_at | date: 'short' }}</td>
                <td class="muted">{{ d.finished_at ? (d.finished_at | date: 'short') : '—' }}</td>
                <td class="muted">{{ d.message || '—' }}</td>
                <td><eg-status [status]="d.status" /></td>
              </tr>
            } @empty {
              @if (loaded()) {
                <tr><td colspan="8" class="empty">Aún no hay despliegues. Elige un modelo aprobado y un dispositivo para lanzar el primero.</td></tr>
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

  protected readonly deployable = computed(() => this.models().filter((m) => m.status !== 'retired'));

  ngOnInit(): void {
    this.loadDeployments();
    this.api.models().subscribe((m) => this.models.set(m));
    this.api.devices().subscribe((d) => this.devices.set(this.live.merge(d)));
    this.live.events$
      .pipe(
        filter((e) => e.type === 'deployment'),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe(() => this.loadDeployments());
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
    this.busy.set(true);
    this.api.deploy(model, device).subscribe({
      next: () => {
        this.busy.set(false);
        this.policy.set(null);
        this.modelId.set(null);
        this.deviceId.set(null);
        this.loadDeployments();
      },
      error: (err) => {
        this.busy.set(false);
        const e = describeError(err);
        this.error.set([e.message, ...e.violations].join(' · '));
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
