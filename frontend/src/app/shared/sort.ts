import { signal } from '@angular/core';

export type SortDir = 'asc' | 'desc';

export class SortState<K extends string> {
  readonly key = signal<K | null>(null);
  readonly dir = signal<SortDir>('desc');

  constructor(initial?: K, dir: SortDir = 'desc') {
    if (initial) {
      this.key.set(initial);
      this.dir.set(dir);
    }
  }

  toggle(key: K): void {
    if (this.key() !== key) {
      this.key.set(key);
      this.dir.set('desc');
    } else if (this.dir() === 'desc') {
      this.dir.set('asc');
    } else {
      this.key.set(null);
    }
  }

  ariaSort(key: K): 'ascending' | 'descending' | 'none' {
    if (this.key() !== key) return 'none';
    return this.dir() === 'asc' ? 'ascending' : 'descending';
  }

  indicator(key: K): string {
    if (this.key() !== key) return '';
    return this.dir() === 'asc' ? '▲' : '▼';
  }

  apply<T>(list: T[], accessors: Record<K, (row: T) => string | number | null | undefined>): T[] {
    const key = this.key();
    if (!key) return list;
    const get = accessors[key];
    const sign = this.dir() === 'asc' ? 1 : -1;
    return [...list].sort((a, b) => {
      const va = get(a);
      const vb = get(b);
      if (va === null || va === undefined) return vb === null || vb === undefined ? 0 : 1;
      if (vb === null || vb === undefined) return -1;
      if (typeof va === 'number' && typeof vb === 'number') return (va - vb) * sign;
      return String(va).localeCompare(String(vb), 'es', { numeric: true }) * sign;
    });
  }
}

export function matchesQuery(query: string, ...fields: (string | null | undefined)[]): boolean {
  const norm = (s: string) => s.normalize('NFD').replace(/\p{Diacritic}/gu, '').toLowerCase();
  const words = norm(query).split(/\s+/).filter(Boolean);
  if (!words.length) return true;
  const haystack = norm(fields.filter(Boolean).join(' '));
  return words.every((w) => haystack.includes(w));
}
