import { Directive, ElementRef, OnDestroy, effect, inject, input } from '@angular/core';

const DURATION_MS = 900;

@Directive({ selector: '[egCount]' })
export class CountUpDirective implements OnDestroy {
  readonly egCount = input<number | null>(null);
  readonly decimals = input(0);
  readonly pad = input(0);

  private readonly el = inject(ElementRef<HTMLElement>);
  private current = 0;
  private frame = 0;
  private readonly reduced =
    typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches;

  constructor() {
    effect(() => this.animateTo(this.egCount()));
  }

  ngOnDestroy(): void {
    cancelAnimationFrame(this.frame);
  }

  format(value: number | null): string {
    if (value === null || Number.isNaN(value)) return '—';
    const text = value.toFixed(this.decimals());
    const [int, dec] = text.split('.');
    const padded = int.padStart(this.pad(), '0');
    return dec ? `${padded}.${dec}` : padded;
  }

  private animateTo(target: number | null): void {
    cancelAnimationFrame(this.frame);
    const node = this.el.nativeElement;
    if (target === null || this.reduced || typeof requestAnimationFrame !== 'function') {
      node.textContent = this.format(target);
      if (target !== null) this.current = target;
      return;
    }
    const from = this.current;
    const start = performance.now();
    const step = (now: number) => {
      const t = Math.min(1, (now - start) / DURATION_MS);
      const eased = 1 - Math.pow(1 - t, 4);
      const value = from + (target - from) * eased;
      node.textContent = this.format(value);
      if (t < 1) this.frame = requestAnimationFrame(step);
      else this.current = target;
    };
    this.frame = requestAnimationFrame(step);
  }
}
