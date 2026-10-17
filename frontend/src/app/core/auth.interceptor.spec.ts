import { HttpClient, provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { session } from '../../testing/helpers';
import { authInterceptor } from './auth.interceptor';
import { AuthService } from './auth.service';

describe('authInterceptor', () => {
  let http: HttpClient;
  let ctrl: HttpTestingController;
  let auth: AuthService;

  beforeEach(() => {
    localStorage.setItem('eg.session', JSON.stringify(session('viewer')));
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(withInterceptors([authInterceptor])),
        provideHttpClientTesting(),
        provideRouter([{ path: 'login', children: [] }]),
      ],
    });
    http = TestBed.inject(HttpClient);
    ctrl = TestBed.inject(HttpTestingController);
    auth = TestBed.inject(AuthService);
  });

  afterEach(() => {
    ctrl.verify();
    localStorage.clear();
  });

  it('añade el Bearer a las llamadas a la API', () => {
    http.get('/api/devices').subscribe();
    const req = ctrl.expectOne('/api/devices');
    expect(req.request.headers.get('Authorization')).toBe(`Bearer ${auth.token()}`);
    req.flush([]);
  });

  it('no filtra el token a otros dominios', () => {
    http.get('https://example.com/data').subscribe();
    const req = ctrl.expectOne('https://example.com/data');
    expect(req.request.headers.has('Authorization')).toBe(false);
    req.flush({});
  });

  it('cierra la sesión ante un 401', () => {
    http.get('/api/devices').subscribe({ error: () => undefined });
    ctrl.expectOne('/api/devices').flush(null, { status: 401, statusText: 'Unauthorized' });
    expect(auth.isAuthenticated()).toBe(false);
  });

  it('no cierra la sesión por un 403', () => {
    http.get('/api/audit').subscribe({ error: () => undefined });
    ctrl.expectOne('/api/audit').flush(null, { status: 403, statusText: 'Forbidden' });
    expect(auth.isAuthenticated()).toBe(true);
  });
});
