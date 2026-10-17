/** Un color estable por dispositivo para que las series coincidan en todas las vistas.
 *  Tonos apagados y distintos de los colores de estado. */
export const DEVICE_COLORS: Record<string, string> = {
  'rpi5-vision': '#6fa8dc',
  'rpi5-genai': '#b392c9',
  'rpi5-agent': '#5fbfb1',
  'uno-q': '#9bbf6b',
  ventuno: '#d4a373',
  'esp32-env': '#d47f8a',
};

const FALLBACK = ['#7fb3d5', '#c39bd3', '#76c7b7', '#b5c99a', '#e0b88a', '#e39aa3'];

export function colorFor(deviceId: string): string {
  if (DEVICE_COLORS[deviceId]) return DEVICE_COLORS[deviceId];
  let hash = 0;
  for (const ch of deviceId) hash = (hash * 31 + ch.charCodeAt(0)) >>> 0;
  return FALLBACK[hash % FALLBACK.length];
}

/** Mismos valores que las variables CSS de styles.scss. */
export const STATUS = {
  accent: '#3cb4cb',
  ok: '#43a971',
  warn: '#d29b34',
  crit: '#dd5a5f',
  muted: '#4b5768',
};

/** Acento en condiciones normales; ámbar o rojo al cruzar los umbrales. */
export function levelColor(value: number | null, warnAt: number, critAt: number): string {
  if (value === null) return STATUS.accent;
  if (value >= critAt) return STATUS.crit;
  if (value >= warnAt) return STATUS.warn;
  return STATUS.accent;
}

export const CHART_TEXT = '#8b97a8';
export const CHART_GRID = 'rgba(148, 163, 184, 0.1)';
