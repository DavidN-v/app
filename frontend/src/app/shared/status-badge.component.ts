import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

/** Texto en español de cada estado. */
const LABELS: Record<string, string> = {
  online: 'En línea',
  offline: 'Sin conexión',
  draft: 'Borrador',
  approved: 'Aprobado',
  deployed: 'Desplegado',
  retired: 'Retirado',
  pending: 'Pendiente',
  succeeded: 'Completado',
  failed: 'Fallido',
  open: 'Abierta',
  acknowledged: 'Reconocida',
  resolved: 'Resuelta',
  info: 'Info',
  warning: 'Aviso',
  critical: 'Crítica',
};

/** Color de cada estado: verde bien, cian informativo, ámbar pendiente, rojo problema. */
const TONES: Record<string, string> = {
  online: 'green', deployed: 'green', succeeded: 'green', resolved: 'green',
  approved: 'cyan', info: 'cyan', acknowledged: 'cyan',
  draft: 'amber', pending: 'amber', warning: 'amber', open: 'amber',
  offline: 'red', failed: 'red', critical: 'red',
  retired: 'muted',
};

/** Etiqueta de estado con su color, usada en todas las tablas. */
@Component({
  selector: 'eg-status',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `<span class="badge" [class]="'badge-' + tone()"><i></i>{{ label() }}</span>`,
})
export class StatusBadgeComponent {
  readonly status = input.required<string>();
  readonly label = computed(() => LABELS[this.status()] ?? this.status());
  readonly tone = computed(() => TONES[this.status()] ?? 'muted');
}
