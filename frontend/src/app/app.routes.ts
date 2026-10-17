import { Routes } from '@angular/router';
import { authGuard, roleGuard } from './core/auth.guard';
import { ShellComponent } from './layout/shell.component';

/**
 * Rutas de la consola.
 *
 * Todas las páginas internas cuelgan de ShellComponent (menú lateral y cabecera) y exigen sesión.
 * Cada página se carga solo cuando se visita por primera vez (loadComponent), lo que reduce
 * el tamaño de la descarga inicial.
 */
export const routes: Routes = [
  {
    path: 'login',
    title: 'Entrar · Edge Governance',
    loadComponent: () => import('./pages/login/login.component').then((m) => m.LoginComponent),
  },
  {
    path: '',
    component: ShellComponent,
    canActivate: [authGuard],
    children: [
      {
        path: '',
        title: 'Vista general · Edge Governance',
        loadComponent: () => import('./pages/overview/overview.component').then((m) => m.OverviewComponent),
      },
      {
        path: 'devices',
        title: 'Dispositivos · Edge Governance',
        loadComponent: () => import('./pages/devices/devices.component').then((m) => m.DevicesComponent),
      },
      {
        path: 'models',
        title: 'Modelos · Edge Governance',
        loadComponent: () => import('./pages/models/models.component').then((m) => m.ModelsComponent),
      },
      {
        path: 'deployments',
        title: 'Despliegues · Edge Governance',
        loadComponent: () =>
          import('./pages/deployments/deployments.component').then((m) => m.DeploymentsComponent),
      },
      {
        path: 'alerts',
        title: 'Alertas · Edge Governance',
        loadComponent: () => import('./pages/alerts/alerts.component').then((m) => m.AlertsComponent),
      },
      {
        path: 'audit',
        title: 'Auditoría · Edge Governance',
        // La auditoría solo la pueden consultar aprobadores y administradores
        canActivate: [roleGuard('approver')],
        loadComponent: () => import('./pages/audit/audit.component').then((m) => m.AuditComponent),
      },
      {
        path: 'policies',
        title: 'Políticas · Edge Governance',
        loadComponent: () => import('./pages/policies/policies.component').then((m) => m.PoliciesComponent),
      },
      {
        path: '**',
        title: 'Página no encontrada · Edge Governance',
        loadComponent: () => import('./pages/not-found.component').then((m) => m.NotFoundComponent),
      },
    ],
  },
];
