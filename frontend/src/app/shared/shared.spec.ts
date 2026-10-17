import { HttpErrorResponse } from '@angular/common/http';
import { TestBed } from '@angular/core/testing';
import { describeError } from './errors';
import { colorFor, DEVICE_COLORS, levelColor, STATUS } from './palette';
import { StatusBadgeComponent } from './status-badge.component';
import { timeAgo } from './time-ago.pipe';

describe('timeAgo', () => {
  const now = Date.parse('2026-01-01T12:00:00Z');
  it.each([
    ['2026-01-01T12:00:00Z', 'ahora'],
    ['2026-01-01T11:59:30Z', 'hace 30s'],
    ['2026-01-01T11:45:00Z', 'hace 15 min'],
    ['2026-01-01T09:00:00Z', 'hace 3 h'],
    ['2025-12-30T12:00:00Z', 'hace 2 d'],
  ])('%s → %s', (iso, expected) => expect(timeAgo(iso, now)).toBe(expected));

  it('trata fechas sin zona como UTC', () => {
    expect(timeAgo('2026-01-01T11:59:30', now)).toBe('hace 30s');
  });

  it('maneja null', () => expect(timeAgo(null)).toBe('nunca'));
});

describe('describeError', () => {
  it('extrae las violaciones de política', () => {
    const err = new HttpErrorResponse({
      status: 422,
      error: { detail: { message: 'Bloqueado por políticas', violations: ['sin firma'] } },
    });
    expect(describeError(err)).toEqual({ message: 'Bloqueado por políticas', violations: ['sin firma'] });
  });

  it('usa el detail textual', () => {
    const err = new HttpErrorResponse({ status: 409, error: { detail: 'Ya existe' } });
    expect(describeError(err).message).toBe('Ya existe');
  });

  it('traduce errores de validación de FastAPI', () => {
    const err = new HttpErrorResponse({ status: 422, error: { detail: [{ msg: 'campo requerido' }] } });
    expect(describeError(err).violations).toEqual(['campo requerido']);
  });

  it('detecta API caída', () => {
    expect(describeError(new HttpErrorResponse({ status: 0 })).message).toContain('No se pudo');
  });
});

describe('colorFor', () => {
  it('es estable y usa la paleta conocida', () => {
    expect(colorFor('rpi5-vision')).toBe(DEVICE_COLORS['rpi5-vision']);
    expect(colorFor('desconocido')).toBe(colorFor('desconocido'));
  });
});

describe('StatusBadgeComponent', () => {
  it('traduce el estado y aplica el tono', () => {
    const fixture = TestBed.createComponent(StatusBadgeComponent);
    fixture.componentRef.setInput('status', 'failed');
    fixture.detectChanges();
    const el: HTMLElement = fixture.nativeElement.querySelector('.badge');
    expect(el.textContent?.trim()).toBe('Fallido');
    expect(el.classList).toContain('badge-red');
  });
});

describe('levelColor', () => {
  it('usa el acento hasta el umbral y luego ámbar y rojo', () => {
    expect(levelColor(40, 75, 90)).toBe(STATUS.accent);
    expect(levelColor(80, 75, 90)).toBe(STATUS.warn);
    expect(levelColor(95, 75, 90)).toBe(STATUS.crit);
    expect(levelColor(null, 75, 90)).toBe(STATUS.accent);
  });
});
