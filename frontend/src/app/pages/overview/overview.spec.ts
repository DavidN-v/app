import { toLogLine } from './overview.component';

describe('toLogLine', () => {
  const now = new Date('2026-10-17T10:30:12.431Z');

  it('formatea telemetría con la hora UTC en milisegundos', () => {
    const l = toLogLine({ type: 'telemetry', data: { id: 'uno-q', cpu: 8.4, ram: 18, temp: 39.2, ts: '' } }, 1, now)!;
    expect(l).toMatchObject({ time: '10:30:12.431', who: 'uno-q', kind: 'TEL', hot: false });
    expect(l.msg).toBe('cpu 8% ram 18% t 39.2°');
  });

  it('marca en rojo la latencia por encima del umbral', () => {
    const l = toLogLine({ type: 'inference', data: { id: 'ventuno', latency_ms: 152, confidence: null, model: 'anomaly-ts:2.0' } }, 2, now)!;
    expect(l.hot).toBe(true);
    expect(l.msg).toBe('anomaly-ts:2.0 152.0ms');
  });

  it('las alertas y las caídas de enlace son siempre destacadas', () => {
    expect(toLogLine({ type: 'device_status', data: { id: 'esp32-env', status: 'offline' } }, 3, now)!.hot).toBe(true);
    expect(toLogLine({ type: 'device_status', data: { id: 'esp32-env', status: 'online' } }, 4, now)!.hot).toBe(false);
  });

  it('ignora los ping', () => {
    expect(toLogLine({ type: 'ping' }, 5, now)).toBeNull();
  });
});
