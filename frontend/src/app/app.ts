import { Component } from '@angular/core';
import { RouterOutlet } from '@angular/router';

/** Componente raíz: solo muestra la página que corresponde a la ruta actual. */
@Component({
  selector: 'app-root',
  imports: [RouterOutlet],
  template: '<router-outlet />',
})
export class App {}
