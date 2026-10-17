import { Injectable, computed, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import { Observable, tap } from 'rxjs';
import { ApiService } from './api.service';
import { Role, Session } from './models';

const STORAGE_KEY = 'eg.session';
const ROLE_LEVEL: Record<Role, number> = { viewer: 0, operator: 1, approver: 2, admin: 3 };

function readStored(): Session | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const session = JSON.parse(raw) as Session;
    return isExpired(session.access_token) ? null : session;
  } catch {
    return null;
  }
}

/** Lee `exp` del JWT sin validarlo (la validación real la hace el backend). */
export function isExpired(token: string, now = Date.now()): boolean {
  try {
    const payload = JSON.parse(atob(token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')));
    return typeof payload.exp !== 'number' || payload.exp * 1000 <= now;
  } catch {
    return true;
  }
}

@Injectable({ providedIn: 'root' })
export class AuthService {
  private readonly api = inject(ApiService);
  private readonly router = inject(Router);
  private readonly session = signal<Session | null>(readStored());

  readonly user = computed(() => this.session());
  readonly isAuthenticated = computed(() => this.session() !== null);
  readonly token = computed(() => this.session()?.access_token ?? null);

  login(username: string, password: string): Observable<Session> {
    return this.api.login(username, password).pipe(
      tap((s) => {
        this.session.set(s);
        try {
          localStorage.setItem(STORAGE_KEY, JSON.stringify(s));
        } catch {
          /* almacenamiento no disponible: la sesión vive solo en memoria */
        }
      }),
    );
  }

  logout(): void {
    this.session.set(null);
    try {
      localStorage.removeItem(STORAGE_KEY);
    } catch {
      /* noop */
    }
    void this.router.navigate(['/login']);
  }

  /** ¿El usuario tiene al menos este rol? */
  can(minimum: Role): boolean {
    const role = this.session()?.role;
    return role !== undefined && ROLE_LEVEL[role] >= ROLE_LEVEL[minimum];
  }
}
