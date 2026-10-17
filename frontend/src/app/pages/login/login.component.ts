import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { Router } from '@angular/router';
import { AuthService } from '../../core/auth.service';
import { describeError } from '../../shared/errors';

@Component({
  selector: 'eg-login',
  imports: [ReactiveFormsModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="login-page">
      <section class="login-intro">
        <span class="login-name">Edge Governance</span>
        <div>
          <h1>Tus modelos en el edge, bajo control</h1>
          <p>
            Telemetría en vivo de cada placa, aprobación de versiones y despliegues que solo pasan si
            cumplen las políticas.
          </p>
          <ul class="login-facts">
            <li>Latencia, temperatura y drift de cada dispositivo en tiempo real.</li>
            <li>Ningún modelo se despliega sin firma, licencia válida y aprobación de otra persona.</li>
            <li>Cada acción queda en un registro de auditoría que no se puede alterar.</li>
          </ul>
        </div>
        <span class="muted small">Raspberry Pi · Arduino · ESP32</span>
      </section>

      <main class="login-panel">
        <form class="login-form" [formGroup]="form" (ngSubmit)="submit()" novalidate>
          <h2>Entrar a la consola</h2>
          <label>
            Usuario
            <input formControlName="username" autocomplete="username" [attr.aria-invalid]="invalid('username')" />
            @if (invalid('username')) {
              <span class="form-error">Escribe tu usuario.</span>
            }
          </label>
          <label>
            Contraseña
            <input
              type="password"
              formControlName="password"
              autocomplete="current-password"
              [attr.aria-invalid]="invalid('password')"
            />
            @if (invalid('password')) {
              <span class="form-error">Escribe tu contraseña.</span>
            }
          </label>
          @if (error()) {
            <p class="form-error" role="alert">{{ error() }}</p>
          }
          <button class="btn btn-primary" type="submit" [disabled]="loading()">
            {{ loading() ? 'Entrando…' : 'Entrar' }}
          </button>
          <p class="login-hint">
            Demo: admin, approver, operator o viewer. La contraseña es el usuario seguido de 123.
          </p>
        </form>
      </main>
    </div>
  `,
})
export class LoginComponent {
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);
  protected readonly loading = signal(false);
  protected readonly error = signal('');

  protected readonly form = inject(FormBuilder).nonNullable.group({
    username: ['', Validators.required],
    password: ['', Validators.required],
  });

  protected invalid(name: 'username' | 'password'): boolean {
    const c = this.form.controls[name];
    return c.invalid && c.touched;
  }

  submit(): void {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }
    const { username, password } = this.form.getRawValue();
    this.loading.set(true);
    this.error.set('');
    this.auth.login(username, password).subscribe({
      next: () => void this.router.navigate(['/']),
      error: (err) => {
        this.error.set(describeError(err).message);
        this.loading.set(false);
      },
    });
  }
}
