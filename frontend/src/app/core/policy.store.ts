import { Injectable, computed, inject, signal } from '@angular/core';
import { ApiService } from './api.service';
import { Policy } from './models';

export interface Threshold {
  value: number;
  unit: string;
  policy: string | null;
}

@Injectable({ providedIn: 'root' })
export class PolicyStore {
  private readonly api = inject(ApiService);
  readonly policies = signal<Policy[]>([]);
  private loading = false;

  private num(key: string, fallback: number): number {
    const p = this.policies().find((x) => x.key === key && x.enabled);
    const v = p ? Number(p.value) : NaN;
    return Number.isFinite(v) ? v : fallback;
  }

  readonly thresholds = computed<Record<'cpu' | 'ram' | 'temp' | 'latency', Threshold>>(() => ({
    cpu: { value: this.num('max_cpu_pct', 90), unit: '%', policy: 'max_cpu_pct' },
    ram: { value: this.num('max_ram_pct', 85), unit: '%', policy: 'max_ram_pct' },
    temp: { value: this.num('max_temp_c', 75), unit: '°C', policy: 'max_temp_c' },
    latency: { value: this.num('max_latency_ms', 100), unit: 'ms', policy: 'max_latency_ms' },
  }));

  ensureLoaded(): void {
    if (this.policies().length || this.loading) return;
    this.refresh();
  }

  refresh(): void {
    this.loading = true;
    this.api.policies().subscribe({
      next: (p) => {
        this.policies.set(p);
        this.loading = false;
      },
      error: () => (this.loading = false),
    });
  }

  upsert(policy: Policy): void {
    this.policies.update((list) => {
      const found = list.some((p) => p.key === policy.key);
      return found ? list.map((p) => (p.key === policy.key ? policy : p)) : [...list, policy];
    });
  }

  tip(metric: 'cpu' | 'ram' | 'temp' | 'latency', value: number | null): string | null {
    const t = this.thresholds()[metric];
    if (value === null || value <= t.value) return null;
    return `Límite ${t.value}${t.unit === '%' ? ' %' : ' ' + t.unit} · política ${t.policy}`;
  }

  over(metric: 'cpu' | 'ram' | 'temp' | 'latency', value: number | null): boolean {
    return value !== null && value > this.thresholds()[metric].value;
  }
}
