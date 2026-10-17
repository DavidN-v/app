import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { ToastService } from './toast.service';

const TAG = { ok: 'OK', info: 'INFO', warn: 'AVISO', crit: 'ALERTA' } as const;

@Component({
  selector: 'eg-toasts',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <section class="toasts" aria-live="polite" aria-label="Notificaciones">
      @for (t of toast.toasts(); track t.id) {
        <article class="toast" [class]="'toast toast-' + t.kind" [attr.role]="t.kind === 'crit' ? 'alert' : 'status'">
          <header>
            <span class="toast-tag">[ {{ tag[t.kind] }} ]</span>
            <button class="toast-x" (click)="toast.dismiss(t.id)" aria-label="Cerrar aviso">×</button>
          </header>
          <p class="toast-title">{{ t.title }}</p>
          @if (t.detail) {
            <p class="toast-detail">{{ t.detail }}</p>
          }
          @if (t.action) {
            <button class="btn btn-sm toast-action" (click)="toast.runAction(t)">{{ t.action.label }}</button>
          }
          @if (t.duration > 0) {
            <span class="toast-timer" [style.animation-duration.ms]="t.duration" aria-hidden="true"></span>
          }
        </article>
      }
    </section>
  `,
})
export class ToastHostComponent {
  protected readonly toast = inject(ToastService);
  protected readonly tag = TAG;
}
