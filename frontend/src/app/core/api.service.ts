import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import {
  Alert,
  AuditEntry,
  ChainVerification,
  Deployment,
  Device,
  LatencyHistory,
  LatencyWindow,
  MLModel,
  NewDevice,
  ModelStatus,
  NewModel,
  Overview,
  Policy,
  PolicyCheck,
  Session,
} from './models';

/**
 * Acceso a la API REST del backend.
 *
 * Cada método corresponde a una ruta de la API y devuelve un Observable con la respuesta ya
 * tipada. El token de sesión no se añade aquí sino en auth.interceptor.ts, que lo incluye en
 * todas las peticiones de forma automática.
 */
@Injectable({ providedIn: 'root' })
export class ApiService {
  private readonly http = inject(HttpClient);

  login(username: string, password: string) {
    return this.http.post<Session>('/api/auth/login', { username, password });
  }

  /** Resumen de la vista general: recuentos, medias y latencias recientes. */
  overview() {
    return this.http.get<Overview>('/api/overview');
  }

  /** Historial de latencia para la gráfica (5 min, 1 h o 24 h). */
  latencyHistory(window: LatencyWindow) {
    return this.http.get<LatencyHistory>('/api/metrics/latency', { params: { window } });
  }

  devices() {
    return this.http.get<Device[]>('/api/devices');
  }

  /** Da de alta un dispositivo (solo administradores). */
  registerDevice(body: NewDevice) {
    return this.http.post<Device>('/api/devices', body);
  }

  /** Da de baja un dispositivo (solo administradores). */
  decommissionDevice(id: string) {
    return this.http.delete<void>(`/api/devices/${encodeURIComponent(id)}`);
  }

  models(status?: ModelStatus) {
    const params = status ? new HttpParams().set('status', status) : undefined;
    return this.http.get<MLModel[]>('/api/models', { params });
  }

  registerModel(body: NewModel) {
    return this.http.post<MLModel>('/api/models', body);
  }

  /** Aprueba o retira un modelo; el motivo queda en la auditoría. */
  transitionModel(id: number, to: 'approved' | 'retired', reason = '') {
    return this.http.post<MLModel>(`/api/models/${id}/transition`, { to, reason });
  }

  deployments() {
    return this.http.get<Deployment[]>('/api/deployments');
  }

  /** Comprueba las políticas de un despliegue sin llegar a ejecutarlo. */
  checkDeployment(model_id: number, device_id: string) {
    return this.http.post<PolicyCheck>('/api/deployments/check', { model_id, device_id });
  }

  deploy(model_id: number, device_id: string) {
    return this.http.post<Deployment>('/api/deployments', { model_id, device_id });
  }

  alerts(status?: Alert['status']) {
    const params = status ? new HttpParams().set('status', status) : undefined;
    return this.http.get<Alert[]>('/api/alerts', { params });
  }

  /** Reconoce o resuelve una alerta. */
  actOnAlert(id: number, status: 'acknowledged' | 'resolved') {
    return this.http.post<Alert>(`/api/alerts/${id}/action`, { status });
  }

  policies() {
    return this.http.get<Policy[]>('/api/policies');
  }

  updatePolicy(key: string, patch: Partial<Pick<Policy, 'value' | 'enabled'>>) {
    return this.http.patch<Policy>(`/api/policies/${key}`, patch);
  }

  audit(limit = 200) {
    return this.http.get<AuditEntry[]>('/api/audit', { params: { limit } });
  }

  /** Comprueba la integridad de la cadena de auditoría. */
  verifyAudit() {
    return this.http.get<ChainVerification>('/api/audit/verify');
  }
}
