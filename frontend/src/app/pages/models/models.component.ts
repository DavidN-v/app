import { DatePipe, KeyValuePipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { ApiService } from '../../core/api.service';
import { AuthService } from '../../core/auth.service';
import { MLModel, ModelStatus } from '../../core/models';
import { describeError } from '../../shared/errors';
import { StatusBadgeComponent } from '../../shared/status-badge.component';

type Filter = ModelStatus | 'all';

@Component({
  selector: 'eg-models',
  imports: [StatusBadgeComponent, ReactiveFormsModule, DatePipe, KeyValuePipe],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './models.component.html',
})
export class ModelsComponent implements OnInit {
  private readonly api = inject(ApiService);
  protected readonly auth = inject(AuthService);

  protected readonly models = signal<MLModel[]>([]);
  protected readonly filter = signal<Filter>('all');
  protected readonly selected = signal<MLModel | null>(null);
  protected readonly showForm = signal(false);
  protected readonly error = signal('');
  protected readonly busy = signal(false);
  protected readonly loaded = signal(false);
  protected readonly skeletonRows = [1, 2, 3, 4, 5];
  protected readonly retiring = signal<MLModel | null>(null);
  protected readonly retireReason = signal('');
  protected readonly filters: { key: Filter; label: string }[] = [
    { key: 'all', label: 'Todos' },
    { key: 'draft', label: 'Borradores' },
    { key: 'approved', label: 'Aprobados' },
    { key: 'deployed', label: 'Desplegados' },
    { key: 'retired', label: 'Retirados' },
  ];

  protected readonly visible = computed(() => {
    const f = this.filter();
    return f === 'all' ? this.models() : this.models().filter((m) => m.status === f);
  });
  protected readonly counts = computed(() => {
    const c: Record<string, number> = { all: this.models().length };
    for (const m of this.models()) c[m.status] = (c[m.status] ?? 0) + 1;
    return c;
  });

  protected readonly form = inject(FormBuilder).nonNullable.group({
    name: ['', [Validators.required, Validators.minLength(2)]],
    version: ['', Validators.required],
    framework: ['onnx' as 'onnx' | 'gguf' | 'tflite', Validators.required],
    task: ['', Validators.required],
    artifact_uri: ['', Validators.required],
    sha256: ['', [Validators.required, Validators.pattern(/^[a-f0-9]{64}$/)]],
    signature: [''],
    license: ['apache-2.0', Validators.required],
  });

  ngOnInit(): void {
    this.load();
  }

  load(): void {
    this.api.models().subscribe((m) => {
      this.models.set(m);
      this.loaded.set(true);
      const sel = this.selected();
      if (sel) this.selected.set(m.find((x) => x.id === sel.id) ?? null);
    });
  }

  /** Separación de funciones: nadie aprueba su propio modelo. */
  canApprove(m: MLModel): boolean {
    return m.status === 'draft' && this.auth.can('approver') && m.owner !== this.auth.user()?.username;
  }

  canRetire(m: MLModel): boolean {
    return m.status !== 'retired' && this.auth.can('approver');
  }

  select(m: MLModel): void {
    this.selected.set(m);
    if (this.retiring()?.id !== m.id) this.retiring.set(null);
  }

  /** La retirada pide el motivo dentro de la ficha, no en una ventana del navegador. */
  startRetire(m: MLModel): void {
    this.selected.set(m);
    this.retireReason.set('');
    this.retiring.set(m);
  }

  confirmRetire(m: MLModel): void {
    const reason = this.retireReason().trim();
    if (!reason) return;
    this.transition(m, 'retired', reason);
    this.retiring.set(null);
  }

  transition(m: MLModel, to: 'approved' | 'retired', reason = 'Aprobado desde la consola'): void {
    this.busy.set(true);
    this.api.transitionModel(m.id, to, reason).subscribe({
      next: () => {
        this.busy.set(false);
        this.load();
      },
      error: (err) => {
        this.busy.set(false);
        this.error.set(describeError(err).message);
      },
    });
  }

  submit(): void {
    if (this.form.invalid) return;
    const value = this.form.getRawValue();
    this.busy.set(true);
    this.error.set('');
    this.api.registerModel({ ...value, signature: value.signature || null }).subscribe({
      next: () => {
        this.busy.set(false);
        this.showForm.set(false);
        this.form.reset();
        this.load();
      },
      error: (err) => {
        this.busy.set(false);
        const e = describeError(err);
        this.error.set([e.message, ...e.violations].join(' · '));
      },
    });
  }

  protected isScalar(v: unknown): boolean {
    return typeof v !== 'object' || v === null;
  }
}
