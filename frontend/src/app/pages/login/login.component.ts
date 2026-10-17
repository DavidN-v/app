import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { Router } from '@angular/router';
import { AuthService } from '../../core/auth.service';
import { describeError } from '../../shared/errors';

/** Pantalla de inicio de sesión. */
@Component({
  selector: 'eg-login',
  imports: [ReactiveFormsModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="login-page">
      <section class="login-intro">
        <div class="login-top"><span>Nodo EDGE-GOV-01</span><span>Rev 1.0 · Acceso restringido</span></div>
        <div>
          <h1 class="login-mark" aria-label="Edge Gov">
            <span>Edge<span class="slash">/</span></span>
            <span>Gov</span>
          </h1>
        </div>
        <div>
          <p class="login-lede">
            Gobernanza y observabilidad de modelos de IA en el edge. Telemetría en vivo de cada placa,
            versiones aprobadas por otra persona y despliegues que solo salen si cumplen las políticas.
          </p>
          <ol class="bootlog" aria-hidden="true">
            <li><b>mqtt</b> conectando a edge/# ......... <span class="okk">OK</span></li>
            <li><b>registro</b> modelos firmados ......... <span class="okk">OK</span></li>
            <li><b>políticas</b> firma · licencia · hardware <span class="okk">OK</span></li>
            <li><b>auditoría</b> cadena sha-256 íntegra ... <span class="okk">OK</span></li>
            <li><b>drift</b> monitor psi activo ......... <span class="okk">OK</span></li>
            <li><b>sesión</b> esperando credenciales_</li>
          </ol>
        </div>
        <div class="login-bottom"><span>Raspberry Pi · Arduino · ESP32</span><span>© Edge Governance</span></div>
      </section>

      <main class="login-panel">
        <form class="login-form" [formGroup]="form" (ngSubmit)="submit()" novalidate>
          <h2>Identificación de operador</h2>
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
            {{ loading() ? 'Verificando…' : 'Entrar >>>' }}
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

  /** Indica si un campo debe mostrarse como erróneo (vacío después de intentar entrar). */
  protected invalid(name: 'username' | 'password'): boolean {
    const c = this.form.controls[name];
    return c.invalid && c.touched;
  }

  /** Envía las credenciales; si son correctas, entra en la consola. */
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
