import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { fakeJwt, session } from '../../testing/helpers';
import { AuthService, isExpired } from './auth.service';

describe('AuthService', () => {
  let http: HttpTestingController;

  function setup(): AuthService {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting(), provideRouter([{ path: 'login', children: [] }])],
    });
    http = TestBed.inject(HttpTestingController);
    return TestBed.inject(AuthService);
  }

  beforeEach(() => localStorage.clear());
  afterEach(() => http.verify());

  it('inicia sin sesión', () => {
    const auth = setup();
    expect(auth.isAuthenticated()).toBe(false);
    expect(auth.can('viewer')).toBe(false);
  });

  it('guarda la sesión tras el login', () => {
    const auth = setup();
    auth.login('approver', 'pwd').subscribe();
    const req = http.expectOne('/api/auth/login');
    expect(req.request.body).toEqual({ username: 'approver', password: 'pwd' });
    req.flush(session('approver'));

    expect(auth.isAuthenticated()).toBe(true);
    expect(auth.user()?.role).toBe('approver');
    expect(JSON.parse(localStorage.getItem('eg.session')!).username).toBe('approver');
  });

  it('restaura una sesión válida y descarta una expirada', () => {
    localStorage.setItem('eg.session', JSON.stringify(session('operator')));
    expect(setup().isAuthenticated()).toBe(true);

    TestBed.resetTestingModule();
    localStorage.setItem('eg.session', JSON.stringify({ ...session(), access_token: fakeJwt(-10) }));
    expect(setup().isAuthenticated()).toBe(false);
  });

  it('aplica la jerarquía de roles', () => {
    localStorage.setItem('eg.session', JSON.stringify(session('operator')));
    const auth = setup();
    expect(auth.can('viewer')).toBe(true);
    expect(auth.can('operator')).toBe(true);
    expect(auth.can('approver')).toBe(false);
    expect(auth.can('admin')).toBe(false);
  });

  it('logout limpia todo', () => {
    localStorage.setItem('eg.session', JSON.stringify(session()));
    const auth = setup();
    auth.logout();
    expect(auth.isAuthenticated()).toBe(false);
    expect(localStorage.getItem('eg.session')).toBeNull();
  });
});

describe('isExpired', () => {
  it('detecta tokens caducados, válidos y corruptos', () => {
    expect(isExpired(fakeJwt(60))).toBe(false);
    expect(isExpired(fakeJwt(-60))).toBe(true);
    expect(isExpired('basura')).toBe(true);
  });
});
