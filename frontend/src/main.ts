import { bootstrapApplication } from '@angular/platform-browser';
import { appConfig } from './app/app.config';
import { App } from './app/app';

// Punto de entrada: arranca la aplicación Angular con su configuración
bootstrapApplication(App, appConfig)
  .catch((err) => console.error(err));
