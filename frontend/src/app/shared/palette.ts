/** Un color propio por dispositivo, igual en la gráfica, la tabla, las tarjetas y el registro.
 *  El rojo queda fuera de la paleta: está reservado para lo que exige atención. */
export const DEVICE_COLORS: Record<string, string> = {
  'rpi5-vision': '#38bdf8',
  'rpi5-genai': '#c084fc',
  'rpi5-agent': '#34d399',
  'uno-q': '#facc15',
  ventuno: '#fb923c',
  'esp32-env': '#f472b6',
};

const FALLBACK = ['#22d3ee', '#a3e635', '#818cf8', '#fbbf24', '#2dd4bf', '#e879f9'];

export function colorFor(deviceId: string): string {
  if (DEVICE_COLORS[deviceId]) return DEVICE_COLORS[deviceId];
  let hash = 0;
  for (const ch of deviceId) hash = (hash * 31 + ch.charCodeAt(0)) >>> 0;
  return FALLBACK[hash % FALLBACK.length];
}

/** Mismos valores que las variables CSS de styles.scss. */
export const STATUS = {
  accent: '#4af626',
  ok: '#4af626',
  warn: '#ff2a2a',
  crit: '#ff2a2a',
  muted: '#46505f',
};

/** Verde en condiciones normales; rojo al cruzar el umbral de aviso. */
export function levelColor(value: number | null, warnAt: number, critAt: number): string {
  if (value === null) return STATUS.accent;
  if (value >= critAt) return STATUS.crit;
  if (value >= warnAt) return STATUS.warn;
  return STATUS.accent;
}

export const CHART_TEXT = '#788292';
export const CHART_GRID = '#2a303a';
