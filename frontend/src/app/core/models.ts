
export type Role = 'admin' | 'approver' | 'operator' | 'viewer';
export type ModelStatus = 'draft' | 'approved' | 'deployed' | 'retired';
export type Severity = 'info' | 'warning' | 'critical';

export interface Session {
  access_token: string;
  username: string;
  role: Role;
}

export interface ModelBrief {
  id: number;
  name: string;
  version: string;
  framework: string;
}

export interface Device {
  id: string;
  name: string;
  kind: 'rpi5' | 'arduino' | 'esp32';
  role: string;
  location: string;
  status: 'online' | 'offline';
  last_seen: string | null;
  cpu: number | null;
  ram: number | null;
  temp: number | null;
  latency_ms: number | null;
  current_model: ModelBrief | null;
}

export type NewDevice = Pick<Device, 'id' | 'name' | 'kind' | 'role' | 'location'>;

export interface MLModel extends ModelBrief {
  task: string;
  artifact_uri: string;
  sha256: string;
  signature: string | null;
  license: string;
  owner: string;
  metrics: Record<string, unknown>;
  status: ModelStatus;
  approved_by: string | null;
  approved_at: string | null;
  created_at: string;
}

export type NewModel = Pick<
  MLModel,
  'name' | 'version' | 'framework' | 'task' | 'artifact_uri' | 'sha256' | 'signature' | 'license'
> & { metrics?: Record<string, unknown> };

export type DeployStage = 'requested' | 'downloading' | 'verifying' | 'installing' | 'confirmed' | 'failed';

export interface Deployment {
  id: number;
  model: ModelBrief;
  device_id: string;
  status: 'pending' | 'succeeded' | 'failed';
  stage: DeployStage;
  requested_by: string;
  message: string;
  created_at: string;
  finished_at: string | null;
}

export interface PolicyCheck {
  allowed: boolean;
  violations: string[];
}

export interface Alert {
  id: number;
  device_id: string | null;
  severity: Severity;
  kind: string;
  message: string;
  status: 'open' | 'acknowledged' | 'resolved';
  created_at: string;
  handled_by?: string | null;
}

export interface Policy {
  key: string;
  value: string;
  description: string;
  enabled: boolean;
}

export interface AuditEntry {
  id: number;
  ts: string;
  actor: string;
  action: string;
  entity: string;
  entity_id: string;
  details: Record<string, unknown>;
  prev_hash: string;
  hash: string;
}

export interface ChainVerification {
  valid: boolean;
  entries: number;
  broken_at: number | null;
}

export type LatencyWindow = '5m' | '1h' | '24h';

export interface LatencyHistory {
  window: LatencyWindow;
  series: Record<string, Point[]>;
}

export type Point = [number, number];

export interface Overview {
  devices: { total: number; online: number };
  models: { total: number; by_status: Partial<Record<ModelStatus, number>> };
  deployments: { pending: number; failed: number };
  alerts_open: number;
  avg: { latency_ms: number | null; cpu: number | null; ram: number | null; temp: number | null };
  latency_series: Record<string, Point[]>;
}

export type LiveEvent =
  | { type: 'telemetry'; data: { id: string; cpu: number; ram: number; temp: number | null; ts: string } }
  | { type: 'inference'; data: { id: string; latency_ms: number; confidence: number | null; model: string } }
  | { type: 'device_status'; data: { id: string; status: 'online' | 'offline' } }
  | { type: 'alert'; data: Alert }
  | { type: 'alert_resolved'; data: { ids: number[]; device_id: string | null; kind: string } }
  | { type: 'deployment'; data: { id: number; status: Deployment['status']; stage?: DeployStage } }
  | { type: 'ping' };
