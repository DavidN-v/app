import { Injectable, InjectionToken, signal } from '@angular/core';

export const UNDO_WINDOW_MS = new InjectionToken<number>('UNDO_WINDOW_MS', { factory: () => 5000 });

export type ToastKind = 'ok' | 'info' | 'warn' | 'crit';

export interface ToastAction {
  label: string;
  run: () => void;
}

export interface Toast {
  id: number;
  kind: ToastKind;
  title: string;
  detail?: string;
  action?: ToastAction;
  duration: number;
}

const MAX_VISIBLE = 5;
const DEFAULTS: Record<ToastKind, number> = { ok: 4000, info: 5000, warn: 7000, crit: 0 };

@Injectable({ providedIn: 'root' })
export class ToastService {
  readonly toasts = signal<Toast[]>([]);
  private nextId = 0;
  private readonly timers = new Map<number, ReturnType<typeof setTimeout>>();

  show(kind: ToastKind, title: string, opts: { detail?: string; action?: ToastAction; duration?: number } = {}): number {
    const toast: Toast = { id: ++this.nextId, kind, title, detail: opts.detail, action: opts.action, duration: opts.duration ?? DEFAULTS[kind] };
    this.toasts.update((list) => {
      const next = [toast, ...list];
      for (const dropped of next.slice(MAX_VISIBLE)) this.clearTimer(dropped.id);
      return next.slice(0, MAX_VISIBLE);
    });
    if (toast.duration > 0) this.timers.set(toast.id, setTimeout(() => this.dismiss(toast.id), toast.duration));
    return toast.id;
  }

  ok(title: string, detail?: string, action?: ToastAction): number {
    return this.show('ok', title, { detail, action });
  }

  error(title: string, detail?: string): number {
    return this.show('crit', title, { detail, duration: 8000 });
  }

  dismiss(id: number): void {
    this.clearTimer(id);
    this.toasts.update((list) => list.filter((t) => t.id !== id));
  }

  runAction(toast: Toast): void {
    toast.action?.run();
    this.dismiss(toast.id);
  }

  withUndo(title: string, commit: () => void, opts: { detail?: string; windowMs?: number; onUndo?: () => void } = {}): () => void {
    const windowMs = opts.windowMs ?? 5000;
    if (windowMs <= 0) {
      commit();
      return () => undefined;
    }
    let done = false;
    const timer = setTimeout(() => {
      done = true;
      commit();
    }, windowMs);
    const cancel = () => {
      if (done) return;
      done = true;
      clearTimeout(timer);
      opts.onUndo?.();
    };
    this.show('warn', title, { detail: opts.detail, duration: windowMs, action: { label: 'Deshacer', run: cancel } });
    return cancel;
  }

  private clearTimer(id: number): void {
    const t = this.timers.get(id);
    if (t) clearTimeout(t);
    this.timers.delete(id);
  }
}
