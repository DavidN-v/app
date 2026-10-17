import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { session } from '../../testing/helpers';
import { MLModel, Role } from '../core/models';
import { UNDO_WINDOW_MS } from '../shared/toast.service';
import { DeploymentsComponent, elapsed, stepStates } from './deployments/deployments.component';
import { ModelsComponent } from './models/models.component';

const model = (over: Partial<MLModel> = {}): MLModel => ({
  id: 1, name: 'yolo', version: '8.2', framework: 'onnx', task: 'det', artifact_uri: 'x',
  sha256: 'a'.repeat(64), signature: 'sig', license: 'mit', owner: 'operator', metrics: { mAP50: 0.9 },
  status: 'draft', approved_by: null, approved_at: null, created_at: '2026-01-01T00:00:00Z', ...over,
});

function setup(role: Role, username: string = role) {
  localStorage.setItem('eg.session', JSON.stringify(session(role, username)));
  TestBed.configureTestingModule({
    providers: [provideHttpClient(), provideHttpClientTesting(), provideRouter([]), { provide: UNDO_WINDOW_MS, useValue: 0 }],
  });
  return TestBed.inject(HttpTestingController);
}

afterEach(() => localStorage.clear());

describe('ModelsComponent', () => {
  function render(role: Role, username?: string, models = [model()]) {
    const http = setup(role, username);
    const fixture = TestBed.createComponent(ModelsComponent);
    fixture.detectChanges();
    http.expectOne('/api/models').flush(models);
    fixture.detectChanges();
    return { fixture, http, el: fixture.nativeElement as HTMLElement };
  }

  const buttons = (el: HTMLElement) => [...el.querySelectorAll('button')].map((b) => b.textContent?.trim());

  it('un approver ve "Aprobar" en borradores ajenos', () => {
    expect(buttons(render('approver').el)).toContain('Aprobar');
  });

  it('separación de funciones: el propietario no puede aprobar', () => {
    expect(buttons(render('admin', 'operator').el)).not.toContain('Aprobar');
  });

  it('un viewer no ve acciones ni el botón de registro', () => {
    const b = buttons(render('viewer').el);
    expect(b).not.toContain('Aprobar');
    expect(b).not.toContain('Registrar modelo');
  });

  it('aprobar llama a la API y recarga', () => {
    const { el, http, fixture } = render('approver');
    [...el.querySelectorAll('button')].find((b) => b.textContent?.trim() === 'Aprobar')!.click();
    const req = http.expectOne('/api/models/1/transition');
    expect(req.request.body.to).toBe('approved');
    req.flush(model({ status: 'approved' }));
    http.expectOne('/api/models').flush([model({ status: 'approved' })]);
    fixture.detectChanges();
    expect(el.textContent).toContain('Aprobado');
  });

  it('retirar pide el motivo en la ficha y lo envía a la API', () => {
    const { el, http, fixture } = render('approver', undefined, [model({ status: 'deployed' })]);
    [...el.querySelectorAll('button')].find((b) => b.textContent?.trim() === 'Retirar')!.click();
    fixture.detectChanges();
    const confirm = [...el.querySelectorAll('button')].find((b) => b.textContent?.trim() === 'Retirar modelo')!;
    expect(confirm.disabled).toBe(true);

    const textarea = el.querySelector('textarea')!;
    textarea.value = 'Sustituido por 8.2';
    textarea.dispatchEvent(new Event('input'));
    fixture.detectChanges();
    expect(confirm.disabled).toBe(false);
    confirm.click();

    const req = http.expectOne('/api/models/1/transition');
    expect(req.request.body).toEqual({ to: 'retired', reason: 'Sustituido por 8.2' });
    req.flush(model({ status: 'retired' }));
    http.expectOne('/api/models').flush([model({ status: 'retired' })]);
  });

  it('filtra por estado', () => {
    const { el, fixture } = render('viewer', undefined, [model(), model({ id: 2, status: 'deployed', version: '8.1' })]);
    [...el.querySelectorAll('.tab')].find((t) => t.textContent?.includes('Desplegados'))!.dispatchEvent(new Event('click'));
    fixture.detectChanges();
    expect(el.querySelectorAll('tbody tr').length).toBe(1);
    expect(el.querySelector('tbody')!.textContent).toContain('v8.1');
  });
});

describe('DeploymentsComponent', () => {
  it('muestra las violaciones del dry-run y deshabilita el botón', () => {
    const http = setup('operator');
    const fixture = TestBed.createComponent(DeploymentsComponent);
    fixture.detectChanges();
    http.expectOne('/api/deployments').flush([]);
    http.expectOne('/api/models').flush([model({ status: 'approved' })]);
    http.expectOne('/api/devices').flush([]);

    const cmp = fixture.componentInstance as unknown as {
      modelId: { set(v: number): void };
      deviceId: { set(v: string): void };
      check(): void;
    };
    cmp.modelId.set(1);
    cmp.deviceId.set('esp32-env');
    cmp.check();
    http.expectOne('/api/deployments/check').flush({ allowed: false, violations: ['esp32 no puede ejecutar modelos onnx'] });
    fixture.detectChanges();

    const el: HTMLElement = fixture.nativeElement;
    expect(el.querySelector('.policy-result')!.textContent).toContain('esp32 no puede ejecutar');
    const deployBtn = [...el.querySelectorAll('button')].find((b) => b.textContent?.trim() === 'Desplegar')!;
    expect(deployBtn.disabled).toBe(true);
  });
});

describe('progreso de despliegues', () => {
  it('marca hechas, actual y pendientes según la etapa', () => {
    expect(stepStates({ status: 'pending', stage: 'verifying' })).toEqual(['done', 'done', 'current', 'todo', 'todo']);
  });

  it('un despliegue confirmado completa todos los pasos', () => {
    expect(stepStates({ status: 'succeeded', stage: 'confirmed' })).toEqual(['done', 'done', 'done', 'done', 'done']);
  });

  it('un fallo se marca en la etapa en la que se quedó', () => {
    expect(stepStates({ status: 'failed', stage: 'downloading' })).toEqual(['done', 'fail', 'todo', 'todo', 'todo']);
  });

  it('formatea el tiempo transcurrido', () => {
    expect(elapsed('2026-01-01T00:00:00Z', Date.parse('2026-01-01T00:01:05Z'))).toBe('01:05');
    expect(elapsed('2026-01-01T00:00:00', Date.parse('2026-01-01T00:00:09Z'))).toBe('00:09');
  });
});

describe('ModelsComponent · búsqueda', () => {
  it('filtra por texto sin importar tildes ni mayúsculas', () => {
    const http = setup('viewer');
    const fixture = TestBed.createComponent(ModelsComponent);
    fixture.detectChanges();
    http.expectOne('/api/models').flush([model(), model({ id: 2, name: 'detección-cámara', version: '1.0', license: 'mit' })]);
    fixture.detectChanges();
    const el: HTMLElement = fixture.nativeElement;
    const input = el.querySelector('input[type=search]') as HTMLInputElement;
    input.value = 'DETECCION';
    input.dispatchEvent(new Event('input'));
    fixture.detectChanges();
    expect(el.querySelectorAll('tbody tr').length).toBe(1);
    expect(el.querySelector('tbody')!.textContent).toContain('detección-cámara');
  });
});
