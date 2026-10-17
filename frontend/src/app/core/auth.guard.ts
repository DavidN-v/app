import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { Role } from './models';
import { AuthService } from './auth.service';

/** Protege las páginas internas: sin sesión se redirige a la pantalla de entrada. */
export const authGuard: CanActivateFn = () => {
  const auth = inject(AuthService);
  return auth.isAuthenticated() || inject(Router).createUrlTree(['/login']);
};

/** Protege una página que exige un rol mínimo; si no se tiene, se vuelve a la vista general. */
export const roleGuard =
  (minimum: Role): CanActivateFn =>
  () => {
    const auth = inject(AuthService);
    return auth.can(minimum) || inject(Router).createUrlTree(['/']);
  };
