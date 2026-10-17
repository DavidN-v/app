import { TestBed } from '@angular/core/testing';
import { vi } from 'vitest';
import { titleWithCount } from '../core/notify.service';
import { LogLine, logMatches } from '../pages/overview/overview.component';
import { SortState, matchesQuery } from './sort';
import { ToastService } from './toast.service';

describe('ToastService', () => {
  let toast: ToastService;
  beforeEach(() => {
    vi.useFakeTimers();
    toast = TestBed.inject(ToastService);
  });
  afterEach(() => vi.useRealTimers());

  it('muestra el aviso y lo cierra solo tras su duración', () => {
    toast.ok('Guardado');
    expect(toast.toasts()[0]).toMatchObject({ kind: 'ok', title: 'Guardado' });
    vi.advanceTimersByTime(4100);
    expect(toast.toasts()).toEqual([]);
  });

  it('los críticos se quedan hasta que el usuario los cierra', () => {
    const id = toast.show('crit', 'Temperatura alta');
    vi.advanceTimersByTime(60_000);
    expect(toast.toasts().length).toBe(1);
    toast.dismiss(id);
    expect(toast.toasts()).toEqual([]);
  });

  it('no acumula más de 5 a la vista y el más nuevo va primero', () => {
    for (let i = 1; i <= 7; i++) toast.show('info', `n${i}`);
    expect(toast.toasts().map((t) => t.title)).toEqual(['n7', 'n6', 'n5', 'n4', 'n3']);
  });

  it('withUndo ejecuta la acción al terminar la ventana', () => {
    const commit = vi.fn();
    toast.withUndo('Retirando', commit, { windowMs: 5000 });
    expect(commit).not.toHaveBeenCalled();
    vi.advanceTimersByTime(5000);
    expect(commit).toHaveBeenCalledOnce();
  });

  it('Deshacer cancela la acción y avisa', () => {
    const commit = vi.fn();
    const onUndo = vi.fn();
    toast.withUndo('Retirando', commit, { windowMs: 5000, onUndo });
    toast.runAction(toast.toasts()[0]);
    vi.advanceTimersByTime(10_000);
    expect(commit).not.toHaveBeenCalled();
    expect(onUndo).toHaveBeenCalledOnce();
    expect(toast.toasts()).toEqual([]);
  });
});

describe('SortState', () => {
  type Row = { id: string; cpu: number | null };
  const rows: Row[] = [
    { id: 'b', cpu: 10 },
    { id: 'a', cpu: null },
    { id: 'c', cpu: 90 },
  ];
  const acc = { id: (r: Row) => r.id, cpu: (r: Row) => r.cpu };

  it('primer clic: el peor caso arriba; segundo: ascendente; tercero: sin orden', () => {
    const s = new SortState<'id' | 'cpu'>();
    s.toggle('cpu');
    expect(s.apply(rows, acc).map((r) => r.id)).toEqual(['c', 'b', 'a']);
    s.toggle('cpu');
    expect(s.apply(rows, acc).map((r) => r.id)).toEqual(['b', 'c', 'a']);
    s.toggle('cpu');
    expect(s.apply(rows, acc)).toBe(rows);
  });

  it('los valores vacíos siempre van al final', () => {
    const s = new SortState<'id' | 'cpu'>('cpu', 'asc');
    expect(s.apply(rows, acc).at(-1)!.id).toBe('a');
  });

  it('expone el estado accesible', () => {
    const s = new SortState<'id' | 'cpu'>('cpu');
    expect(s.ariaSort('cpu')).toBe('descending');
    expect(s.ariaSort('id')).toBe('none');
  });
});

describe('matchesQuery', () => {
  it('ignora tildes, mayúsculas y orden de las palabras', () => {
    expect(matchesQuery('camara deteccion', 'Detección', 'cámara frontal')).toBe(true);
    expect(matchesQuery('esp32', 'rpi5-vision')).toBe(false);
    expect(matchesQuery('   ', 'lo que sea')).toBe(true);
  });
});

describe('titleWithCount', () => {
  it('antepone el número de alertas y no lo duplica', () => {
    expect(titleWithCount('Vista general · Edge Governance', 3)).toBe('(3) Vista general · Edge Governance');
    expect(titleWithCount('(3) Vista general', 5)).toBe('(5) Vista general');
    expect(titleWithCount('(3) Vista general', 0)).toBe('Vista general');
  });
});

describe('logMatches', () => {
  const line: LogLine = { id: 1, time: '', who: 'uno-q', device: 'uno-q', kind: 'TEL', msg: '', hot: false };
  it('filtra por tipo y por dispositivo', () => {
    expect(logMatches(line, new Set(['TEL']), null)).toBe(true);
    expect(logMatches(line, new Set(['ALR']), null)).toBe(false);
    expect(logMatches(line, new Set(['TEL']), 'esp32-env')).toBe(false);
  });
});
