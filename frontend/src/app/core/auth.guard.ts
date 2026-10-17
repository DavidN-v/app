import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { Role } from './models';
import { AuthService } from './auth.service';

export const authGuard: CanActivateFn = () => {
  const auth = inject(AuthService);
  return auth.isAuthenticated() || inject(Router).createUrlTree(['/login']);
};

export const roleGuard =
  (minimum: Role): CanActivateFn =>
  () => {
    const auth = inject(AuthService);
    return auth.can(minimum) || inject(Router).createUrlTree(['/']);
  };
