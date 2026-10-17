import { Injectable, OnDestroy, inject, signal } from '@angular/core';
import { Subject } from 'rxjs';
import { AuthService } from './auth.service';
import { Alert, Device, LiveEvent, Point } from './models';

export const SERIES_WINDOW = 600;
const MAX_FEED = 50;
const MAX_BACKOFF_MS = 15_000;

type LivePatch = Partial<Pick<Device, 'cpu' | 'ram' | 'temp' | 'latency_ms' | 'status' | 'last_seen'>>;

@Injectable({ providedIn: 'root' })
export class LiveService implements OnDestroy {
  private readonly auth = inject(AuthService);
  private ws: WebSocket | null = null;
  private retry = 0;
  private retryTimer: ReturnType<typeof setTimeout> | null = null;
  private stopped = true;

  readonly connected = signal(false);
  readonly patches = signal<Record<string, LivePatch>>({});
  readonly latency = signal<Record<string, Point[]>>({});
  readonly alertFeed = signal<Alert[]>([]);
  readonly messagesPerSecond = signal(0);
  readonly events$ = new Subject<LiveEvent>();

  private counter = 0;
  private rateTimer: ReturnType<typeof setInterval> | null = null;

  start(): void {
    if (!this.stopped) return;
    this.stopped = false;
    this.rateTimer = setInterval(() => {
      this.messagesPerSecond.set(this.counter);
      this.counter = 0;
    }, 1000);
    this.open();
  }

  stop(): void {
    this.stopped = true;
    if (this.retryTimer) clearTimeout(this.retryTimer);
    if (this.rateTimer) clearInterval(this.rateTimer);
    this.ws?.close();
    this.ws = null;
    this.connected.set(false);
  }

  ngOnDestroy(): void {
    this.stop();
  }

  seedLatency(series: Record<string, Point[]>): void {
    this.latency.set(
      Object.fromEntries(Object.entries(series).map(([k, v]) => [k, v.slice(-SERIES_WINDOW)])),
    );
  }

  handle(event: LiveEvent): void {
    this.counter++;
    switch (event.type) {
      case 'telemetry': {
        const { id, cpu, ram, temp, ts } = event.data;
        this.patch(id, { cpu, ram, temp, status: 'online', last_seen: ts });
        break;
      }
      case 'inference': {
        const { id, latency_ms } = event.data;
        this.patch(id, { latency_ms });
        const point: Point = [Date.now() / 1000, latency_ms];
        this.latency.update((all) => ({
          ...all,
          [id]: [...(all[id] ?? []), point].slice(-SERIES_WINDOW),
        }));
        break;
      }
      case 'device_status':
        this.patch(event.data.id, { status: event.data.status });
        break;
      case 'alert':
        this.alertFeed.update((feed) => [event.data, ...feed].slice(0, MAX_FEED));
        break;
      case 'alert_resolved': {
        const ids = new Set(event.data.ids);
        this.alertFeed.update((feed) => feed.map((a) => (ids.has(a.id) ? { ...a, status: 'resolved' } : a)));
        break;
      }
    }
    this.events$.next(event);
  }

  merge(devices: Device[]): Device[] {
    const patches = this.patches();
    return devices.map((d) => ({ ...d, ...(patches[d.id] ?? {}) }) as Device);
  }

  private patch(id: string, p: LivePatch): void {
    this.patches.update((all) => ({ ...all, [id]: { ...all[id], ...p } }));
  }

  private open(): void {
    const token = this.auth.token();
    if (!token || this.stopped) return;
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    const ws = new WebSocket(`${proto}://${location.host}/ws?token=${encodeURIComponent(token)}`);
    this.ws = ws;

    ws.onopen = () => {
      this.retry = 0;
      this.connected.set(true);
    };
    ws.onmessage = (msg) => {
      try {
        this.handle(JSON.parse(msg.data as string) as LiveEvent);
      } catch {
        /* mensaje corrupto: se ignora */
      }
    };
    ws.onclose = () => {
      this.connected.set(false);
      if (this.stopped) return;
      const delay = Math.min(MAX_BACKOFF_MS, 500 * 2 ** this.retry++);
      this.retryTimer = setTimeout(() => this.open(), delay);
    };
  }
}
