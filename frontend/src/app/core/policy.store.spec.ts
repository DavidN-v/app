import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { PolicyStore } from './policy.store';

describe('PolicyStore', () => {
  function setup() {
    TestBed.configureTestingModule({ providers: [provideHttpClient(), provideHttpClientTesting()] });
    const store = TestBed.inject(PolicyStore);
    const http = TestBed.inject(HttpTestingController);
    store.ensureLoaded();
    http.expectOne('/api/policies').flush([
      { key: 'max_cpu_pct', value: '75', description: '', enabled: true },
      { key: 'max_temp_c', value: '70', description: '', enabled: false },
    ]);
    return store;
  }

  it('usa el valor de la política y explica el límite', () => {
    const store = setup();
    expect(store.over('cpu', 80)).toBe(true);
    expect(store.over('cpu', 70)).toBe(false);
    expect(store.tip('cpu', 80)).toBe('Límite 75 % · política max_cpu_pct');
    expect(store.tip('cpu', 50)).toBeNull();
  });

  it('una política desactivada vuelve al valor por defecto', () => {
    expect(setup().thresholds().temp.value).toBe(75);
  });

  it('upsert actualiza el umbral al momento', () => {
    const store = setup();
    store.upsert({ key: 'max_cpu_pct', value: '95', description: '', enabled: true });
    expect(store.over('cpu', 80)).toBe(false);
  });
});
