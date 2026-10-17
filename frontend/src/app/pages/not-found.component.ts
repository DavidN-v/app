import { ChangeDetectionStrategy, Component } from '@angular/core';
import { RouterLink } from '@angular/router';

@Component({
  selector: 'eg-not-found',
  imports: [RouterLink],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <section class="not-found">
      <div class="code" aria-hidden="true">404</div>
      <h2>Esta página no existe</h2>
      <p>La dirección no corresponde a ninguna sección de la consola. Puede que el enlace esté mal escrito.</p>
      <a class="btn btn-primary" routerLink="/">Volver a la vista general</a>
    </section>
  `,
})
export class NotFoundComponent {}
