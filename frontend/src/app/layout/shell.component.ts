import { ChangeDetectionStrategy, Component, OnDestroy, OnInit, computed, inject, signal } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { NavigationEnd, Router, RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { filter, map } from 'rxjs';
import { AuthService } from '../core/auth.service';
import { LiveService } from '../core/live.service';
import { Role } from '../core/models';

interface NavItem {
  path: string;
  label: string;
  min?: Role;
}

const ROLE_LABEL: Record<Role, string> = {
  admin: 'Administrador',
  approver: 'Aprobador',
  operator: 'Operador',
  viewer: 'Lector',
};

@Component({
  selector: 'eg-shell',
  imports: [RouterOutlet, RouterLink, RouterLinkActive],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './shell.component.html',
})
export class ShellComponent implements OnInit, OnDestroy {
  protected readonly auth = inject(AuthService);
  protected readonly live = inject(LiveService);
  private readonly router = inject(Router);
  protected readonly menuOpen = signal(false);

  protected readonly nav: NavItem[] = [
    { path: '/', label: 'Vista general' },
    { path: '/devices', label: 'Dispositivos' },
    { path: '/models', label: 'Modelos' },
    { path: '/deployments', label: 'Despliegues' },
    { path: '/alerts', label: 'Alertas' },
    { path: '/audit', label: 'Auditoría', min: 'approver' },
    { path: '/policies', label: 'Políticas' },
  ];

  private readonly url = toSignal(
    this.router.events.pipe(
      filter((e) => e instanceof NavigationEnd),
      map((e) => e.urlAfterRedirects),
    ),
    { initialValue: this.router.url },
  );

  /** El título de la barra es el de la página actual, no el nombre del producto. */
  protected readonly pageTitle = computed(() => {
    const path = this.url().split(/[?#]/)[0];
    return this.nav.find((n) => n.path === path)?.label ?? 'Página no encontrada';
  });

  protected readonly roleLabel = computed(() => {
    const role = this.auth.user()?.role;
    return role ? ROLE_LABEL[role] : '';
  });

  ngOnInit(): void {
    this.live.start();
  }

  ngOnDestroy(): void {
    this.live.stop();
  }

  protected visible(item: NavItem): boolean {
    return !item.min || this.auth.can(item.min);
  }

  protected logout(): void {
    this.live.stop();
    this.auth.logout();
  }
}
