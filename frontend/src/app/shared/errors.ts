import { HttpErrorResponse } from '@angular/common/http';

/** Convierte un error de la API en un mensaje legible (y la lista de violaciones si las hay). */
export function describeError(err: unknown): { message: string; violations: string[] } {
  if (err instanceof HttpErrorResponse) {
    const detail = err.error?.detail;
    if (detail && typeof detail === 'object' && Array.isArray(detail.violations)) {
      return { message: detail.message ?? 'Bloqueado', violations: detail.violations };
    }
    if (typeof detail === 'string') return { message: detail, violations: [] };
    if (Array.isArray(detail)) {
      return { message: 'Datos inválidos', violations: detail.map((d: { msg: string }) => d.msg) };
    }
    if (err.status === 0) return { message: 'No se pudo contactar con la API', violations: [] };
    return { message: `Error ${err.status}`, violations: [] };
  }
  return { message: 'Error inesperado', violations: [] };
}
