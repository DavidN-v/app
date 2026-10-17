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
  ModelStatus,
  NewModel,
  Overview,
  Policy,
  PolicyCheck,
  Session,
} from './models';

@Injectable({ providedIn: 'root' })
export class ApiService {
  private readonly http = inject(HttpClient);

  login(username: string, password: string) {
    return this.http.post<Session>('/api/auth/login', { username, password });
  }

  overview() {
    return this.http.get<Overview>('/api/overview');
  }

  latencyHistory(window: LatencyWindow) {
    return this.http.get<LatencyHistory>('/api/metrics/latency', { params: { window } });
  }

  devices() {
    return this.http.get<Device[]>('/api/devices');
  }

  models(status?: ModelStatus) {
    const params = status ? new HttpParams().set('status', status) : undefined;
    return this.http.get<MLModel[]>('/api/models', { params });
  }

  registerModel(body: NewModel) {
    return this.http.post<MLModel>('/api/models', body);
  }

  transitionModel(id: number, to: 'approved' | 'retired', reason = '') {
    return this.http.post<MLModel>(`/api/models/${id}/transition`, { to, reason });
  }

  deployments() {
    return this.http.get<Deployment[]>('/api/deployments');
  }

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

  verifyAudit() {
    return this.http.get<ChainVerification>('/api/audit/verify');
  }
}
