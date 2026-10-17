import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { ApiService } from '../../core/api.service';
import { AuthService } from '../../core/auth.service';
import { Policy } from '../../core/models';
import { PolicyStore } from '../../core/policy.store';
import { describeError } from '../../shared/errors';
import { ToastService } from '../../shared/toast.service';

/**
 * Página de políticas: un administrador puede cambiar cada valor o activarla y desactivarla.
 * Los demás roles solo pueden consultarlas.
 */
@Component({
  selector: 'eg-policies',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="page-head">
      <div>
        <p class="muted">
          Se aplican en tiempo real a la telemetría y a cada despliegue.
          @if (!auth.can('admin')) { Solo un administrador puede modificarlas. }
        </p>
      </div>
    </div>
    @if (message()) {
      <div class="banner" [class.banner-ok]="!isError()" [class.banner-error]="isError()">{{ message() }}</div>
    }
    <div class="policy-grid">
      @for (p of policies(); track p.key) {
        <div class="card policy" [class.disabled]="!p.enabled">
          <header>
            <code>{{ p.key }}</code>
            <label class="switch">
              <input
                type="checkbox"
                [checked]="p.enabled"
                [disabled]="!auth.can('admin')"
                (change)="save(p, { enabled: $any($event.target).checked })"
              />
              <span></span>
            </label>
          </header>
          <p class="muted">{{ p.description }}</p>
          <div class="policy-edit">
            <input
              #value
              [value]="p.value"
              [disabled]="!auth.can('admin')"
              (keydown.enter)="save(p, { value: value.value })"
            />
            @if (auth.can('admin')) {
              <button class="btn btn-sm btn-ghost" (click)="save(p, { value: value.value })">Guardar</button>
            }
          </div>
        </div>
      }
    </div>
  `,
})
export class PoliciesComponent implements OnInit {
  private readonly api = inject(ApiService);
  protected readonly auth = inject(AuthService);
  private readonly toast = inject(ToastService);
  private readonly store = inject(PolicyStore);
  protected readonly policies = signal<Policy[]>([]);
  protected readonly message = signal('');
  protected readonly isError = signal(false);

  ngOnInit(): void {
    this.api.policies().subscribe((p) => this.policies.set(p));
  }

  /** Guarda el cambio; si undo es verdadero, se trata de deshacer el cambio anterior. */
  save(policy: Policy, patch: Partial<Pick<Policy, 'value' | 'enabled'>>, undo = false): void {
    if (patch.value !== undefined && patch.value === policy.value && patch.enabled === undefined) return;
    const before = { value: policy.value, enabled: policy.enabled };
    this.api.updatePolicy(policy.key, patch).subscribe({
      next: (updated) => {
        this.policies.update((list) => list.map((p) => (p.key === updated.key ? updated : p)));
        this.store.upsert(updated);
        this.message.set('');
        if (undo) {
          this.toast.show('info', `Política ${updated.key} restaurada`);
          return;
        }
        const what = patch.enabled !== undefined
          ? (updated.enabled ? 'activada' : 'desactivada')
          : `${before.value} → ${updated.value}`;
        this.toast.ok(`Política ${updated.key} guardada`, `${what}. Se aplica ya a la telemetría y a los despliegues.`, {
          label: 'Deshacer',
          run: () => this.save(updated, before, true),
        });
      },
      error: (err) => {
        this.isError.set(true);
        this.message.set(describeError(err).message);
        this.toast.error(`No se pudo guardar ${policy.key}`, describeError(err).message);
      },
    });
  }
}
