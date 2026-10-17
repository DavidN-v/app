import { provideHttpClient } from '@angular/common/http';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { LiveService, SERIES_WINDOW } from './live.service';
import { Alert, Device, LiveEvent } from './models';

const device = (id: string, extra: Partial<Device> = {}): Device => ({
  id, name: id, kind: 'rpi5', role: '', location: '', status: 'offline', last_seen: null,
  cpu: null, ram: null, temp: null, latency_ms: null, current_model: null, ...extra,
});

describe('LiveService', () => {
  let live: LiveService;

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideHttpClient(), provideRouter([])] });
    live = TestBed.inject(LiveService);
  });

  it('la telemetría actualiza el dispositivo y lo marca en línea', () => {
    live.handle({ type: 'telemetry', data: { id: 'a', cpu: 12, ram: 30, temp: 50, ts: 'now' } });
    const [merged] = live.merge([device('a')]);
    expect(merged).toMatchObject({ cpu: 12, ram: 30, temp: 50, status: 'online' });
  });

  it('no toca dispositivos sin eventos', () => {
    const [b] = live.merge([device('b', { cpu: 5 })]);
    expect(b.cpu).toBe(5);
  });

  it('las inferencias alimentan la serie de latencia con ventana acotada', () => {
    for (let i = 0; i < SERIES_WINDOW + 20; i++) {
      live.handle({ type: 'inference', data: { id: 'a', latency_ms: i, confidence: null, model: 'm' } });
    }
    const series = live.latency()['a'];
    expect(series.length).toBe(SERIES_WINDOW);
    expect(series.at(-1)![1]).toBe(SERIES_WINDOW + 19);
    expect(live.merge([device('a')])[0].latency_ms).toBe(SERIES_WINDOW + 19);
  });

  it('device_status cambia el estado', () => {
    live.handle({ type: 'device_status', data: { id: 'a', status: 'online' } });
    live.handle({ type: 'device_status', data: { id: 'a', status: 'offline' } });
    expect(live.merge([device('a')])[0].status).toBe('offline');
  });

  it('las alertas nuevas van primero en el feed', () => {
    const alert = (id: number): Alert => ({
      id, device_id: 'a', severity: 'warning', kind: 'k', message: `m${id}`, status: 'open', created_at: '',
    });
    live.handle({ type: 'alert', data: alert(1) });
    live.handle({ type: 'alert', data: alert(2) });
    expect(live.alertFeed().map((a) => a.id)).toEqual([2, 1]);
  });

  it('reemite cada evento por events$', () => {
    const seen: LiveEvent[] = [];
    live.events$.subscribe((e) => seen.push(e));
    live.handle({ type: 'deployment', data: { id: 1, status: 'succeeded' } });
    expect(seen).toHaveLength(1);
  });

  it('seedLatency recorta el histórico a la ventana', () => {
    const long = Array.from({ length: SERIES_WINDOW * 2 }, (_, i) => [i, i] as [number, number]);
    live.seedLatency({ a: long });
    expect(live.latency()['a'].length).toBe(SERIES_WINDOW);
  });
});
