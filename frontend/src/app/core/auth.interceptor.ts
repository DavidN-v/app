import { HttpErrorResponse, HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { catchError, throwError } from 'rxjs';
import { ToastService } from '../shared/toast.service';
import { AuthService } from './auth.service';

export const authInterceptor: HttpInterceptorFn = (req, next) => {
  const auth = inject(AuthService);
  const toast = inject(ToastService);
  const token = auth.token();
  const authed =
    token && req.url.startsWith('/api/')
      ? req.clone({ setHeaders: { Authorization: `Bearer ${token}` } })
      : req;

  return next(authed).pipe(
    catchError((err: unknown) => {
      if (err instanceof HttpErrorResponse && err.status === 401 && !req.url.includes('/auth/')) {
        auth.logout();
      } else if (err instanceof HttpErrorResponse && (err.status === 0 || err.status >= 500)) {
        // Los 4xx los explica cada pantalla; la caída de la API se avisa una sola vez aquí
        toast.error(
          err.status === 0 ? 'Sin conexión con la API' : `La API respondió con error ${err.status}`,
          'Revisa que el servicio esté en marcha e inténtalo de nuevo.',
        );
      }
      return throwError(() => err);
    }),
  );
};
