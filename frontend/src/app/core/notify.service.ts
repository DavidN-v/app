import { DestroyRef, Injectable, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { Title } from '@angular/platform-browser';
import { NavigationEnd, Router } from '@angular/router';
import { Subscription, debounceTime, filter, merge, startWith, switchMap, timer } from 'rxjs';
import { ToastService } from '../shared/toast.service';
import { ApiService } from './api.service';
import { LiveService } from './live.service';

/** Clave donde se guarda si el usuario activó las notificaciones del sistema. */
const PREF_KEY = 'eg.notify';
const STAGE_LABEL: Record<string, string> = {
  confirmed: 'confirmado',
  failed: 'fallido',
};

/** Prefija el título con el número de alertas abiertas: "(3) Vista general · Edge Governance". */
export function titleWithCount(title: string, count: number): string {
  const base = title.replace(/^\(\d+\)\s+/, '');
  return count > 0 ? `(${count}) ${base}` : base;
}

/**
 * Avisos globales, para que lo importante se vea aunque el usuario esté en otra página o pestaña.
 * - Alertas críticas y despliegues terminados como avisos emergentes.
 * - Número de alertas abiertas en el título de la pestaña.
 * - Notificación del sistema si la pestaña está en segundo plano y el usuario lo activó.
 */
@Injectable({ providedIn: 'root' })
export class NotifyService {
  private readonly live = inject(LiveService);
  private readonly api = inject(ApiService);
  private readonly toast = inject(ToastService);
  private readonly title = inject(Title);
  private readonly router = inject(Router);

  readonly openAlerts = signal(0);
  readonly browserEnabled = signal(this.readPref());
  private subs: Subscription[] = [];

  get browserSupported(): boolean {
    return typeof Notification !== 'undefined';
  }

  /** Empieza a escuchar los eventos en vivo. Se llama al entrar en la consola. */
  start(destroyRef: DestroyRef): void {
    this.stop();
    const events = this.live.events$;

    this.subs.push(
      events.pipe(filter((e) => e.type === 'alert'), takeUntilDestroyed(destroyRef)).subscribe((e) => {
        if (e.type !== 'alert') return;
        const a = e.data;
        if (a.severity === 'critical') {
          this.toast.show('crit', a.message, {
            detail: a.device_id ? `Unidad ${a.device_id.toUpperCase()}` : undefined,
            action: { label: 'Ver alertas', run: () => void this.router.navigate(['/alerts']) },
          });
          this.systemNotify('Alerta crítica', a.message);
        } else {
          this.toast.show('warn', a.message, { detail: a.device_id?.toUpperCase() });
        }
      }),
      events.pipe(filter((e) => e.type === 'deployment'), takeUntilDestroyed(destroyRef)).subscribe((e) => {
        if (e.type !== 'deployment' || (e.data.status !== 'succeeded' && e.data.status !== 'failed')) return;
        const ok = e.data.status === 'succeeded';
        const msg = `Despliegue #${e.data.id} ${STAGE_LABEL[ok ? 'confirmed' : 'failed']}`;
        this.toast.show(ok ? 'ok' : 'crit', msg, {
          action: { label: 'Ver despliegues', run: () => void this.router.navigate(['/deployments']) },
        });
        if (!ok) this.systemNotify('Despliegue fallido', msg);
      }),
      // Contador de alertas abiertas: al arrancar, cada minuto y cuando cambian
      merge(timer(0, 60_000), events.pipe(filter((e) => e.type === 'alert' || e.type === 'alert_resolved'), debounceTime(400)))
        .pipe(switchMap(() => this.api.alerts()), takeUntilDestroyed(destroyRef))
        .subscribe((alerts) => {
          this.openAlerts.set(alerts.filter((a) => a.status !== 'resolved').length);
          this.applyTitle();
        }),
      this.router.events
        .pipe(filter((e) => e instanceof NavigationEnd), startWith(null), debounceTime(0), takeUntilDestroyed(destroyRef))
        .subscribe(() => this.applyTitle()),
    );
  }

  /** Deja de escuchar y limpia el título de la pestaña. */
  stop(): void {
    this.subs.forEach((s) => s.unsubscribe());
    this.subs = [];
    this.title.setTitle(titleWithCount(this.title.getTitle(), 0));
  }

  /** Avisa a otras partes de la consola de que el número de alertas pudo cambiar. */
  refreshCount(): void {
    this.api.alerts().subscribe((alerts) => {
      this.openAlerts.set(alerts.filter((a) => a.status !== 'resolved').length);
      this.applyTitle();
    });
  }

  /** Activa o desactiva las notificaciones del sistema; la primera vez el navegador pide permiso. */
  async toggleBrowser(): Promise<void> {
    if (!this.browserSupported) return;
    if (this.browserEnabled()) {
      this.setPref(false);
      this.toast.show('info', 'Notificaciones del sistema desactivadas');
      return;
    }
    const permission = Notification.permission === 'granted' ? 'granted' : await Notification.requestPermission();
    if (permission === 'granted') {
      this.setPref(true);
      this.toast.ok('Notificaciones activadas', 'Te avisaremos de las alertas críticas aunque la pestaña esté en segundo plano.');
    } else {
      this.toast.show('warn', 'El navegador bloqueó las notificaciones', {
        detail: 'Puedes permitirlas desde el candado de la barra de direcciones.',
      });
    }
  }

  private applyTitle(): void {
    this.title.setTitle(titleWithCount(this.title.getTitle(), this.openAlerts()));
  }

  /** Muestra una notificación del sistema operativo, solo si la pestaña no está a la vista. */
  private systemNotify(title: string, body: string): void {
    if (!this.browserEnabled() || !this.browserSupported || Notification.permission !== 'granted') return;
    if (typeof document !== 'undefined' && !document.hidden) return;
    const n = new Notification(`EDGE/GOV · ${title}`, { body, tag: 'edge-gov-alert', icon: '/favicon.svg' });
    n.onclick = () => {
      window.focus();
      void this.router.navigate(['/alerts']);
      n.close();
    };
  }

  private readPref(): boolean {
    try {
      return localStorage.getItem(PREF_KEY) === '1';
    } catch {
      return false;
    }
  }

  private setPref(on: boolean): void {
    this.browserEnabled.set(on);
    try {
      localStorage.setItem(PREF_KEY, on ? '1' : '0');
    } catch {
      /* sin almacenamiento: la preferencia dura la sesión */
    }
  }
}
