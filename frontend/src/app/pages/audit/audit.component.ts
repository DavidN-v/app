import { DatePipe, JsonPipe, SlicePipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { ApiService } from '../../core/api.service';
import { AuditEntry, ChainVerification } from '../../core/models';
import { ToastService } from '../../shared/toast.service';

@Component({
  selector: 'eg-audit',
  imports: [DatePipe, JsonPipe, SlicePipe],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="page-head">
      <div>
        <p class="muted">Registro inmutable: cada entrada incluye el hash SHA-256 de la anterior.</p>
      </div>
      <button class="btn btn-primary" (click)="verify()">Verificar integridad</button>
    </div>

    @if (verification(); as v) {
      <div class="banner" [class.banner-ok]="v.valid" [class.banner-error]="!v.valid">
        @if (v.valid) {
          Cadena íntegra: {{ v.entries }} entradas verificadas.
        } @else {
          Cadena rota en la entrada {{ v.broken_at }}: alguien modificó el registro después de escribirlo.
        }
      </div>
    }

    <div class="card">
      <div class="table-wrap">
        <table class="table">
          <thead>
            <tr><th>#</th><th>Fecha</th><th>Actor</th><th>Acción</th><th>Entidad</th><th>Detalles</th><th>Hash</th></tr>
          </thead>
          <tbody>
          @if (!loaded()) {
            @for (i of skeletonRows; track i) {
              <tr class="skeleton-row"><td colspan="7"><span class="skeleton w-80"></span></td></tr>
            }
          }
            @for (e of entries(); track e.id) {
              <tr>
                <td class="muted tnum">{{ e.id }}</td>
                <td class="muted">{{ e.ts | date: 'medium' }}</td>
                <td><strong>{{ e.actor }}</strong></td>
                <td>{{ e.action }}</td>
                <td class="muted">{{ e.entity }}:{{ e.entity_id }}</td>
                <td class="mono small details">{{ e.details | json }}</td>
                <td class="mono small muted" [title]="e.hash">{{ e.hash | slice: 0 : 12 }}…</td>
              </tr>
            } @empty {
              @if (loaded()) {
                <tr><td colspan="7" class="empty">El registro está vacío.</td></tr>
              }
            }
          </tbody>
        </table>
      </div>
    </div>
  `,
})
export class AuditComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly toast = inject(ToastService);
  protected readonly entries = signal<AuditEntry[]>([]);
  protected readonly loaded = signal(false);
  protected readonly skeletonRows = [1, 2, 3, 4, 5];
  protected readonly verification = signal<ChainVerification | null>(null);

  ngOnInit(): void {
    this.api.audit().subscribe((e) => {
      this.entries.set(e);
      this.loaded.set(true);
    });
  }

  verify(): void {
    this.api.verifyAudit().subscribe((v) => {
      this.verification.set(v);
      if (v.valid) this.toast.ok('Cadena de auditoría íntegra', `${v.entries} entradas verificadas con SHA-256.`);
      else this.toast.error('Registro de auditoría manipulado', `La cadena se rompe en la entrada ${v.broken_at}.`);
    });
  }
}
