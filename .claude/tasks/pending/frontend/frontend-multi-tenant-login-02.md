---
id: frontend-multi-tenant-login-02
package: frontend
plan: multi-tenant-login
status: pending
priority: 1
depends_on: [frontend-multi-tenant-login-01]
estimate: 2h
actual:
created: 2026-08-21
updated: 2026-08-21
---

# UI de cards (shadcn `Card`) de selección de tenant, integrada en el login

## Description

Con `auth-context.tsx` ya devolviendo la rama de selección (`-01`), esta tarea construye la pantalla
que la consume: al recibir `tenantSelection` de `login()`, `login-form.tsx` renderiza una card por
tenant (`shadcn Card`, sin ruta nueva). Elegir una llama a `selectTenant`; en éxito navega a `/` igual
que un login directo; en error, muestra una alerta accesible sobre la propia pantalla de cards (no
vuelve al formulario, no descarta las demás opciones) con un botón "Volver a iniciar sesión" que solo
aparece tras ese error (decisión de `grilling`) y que, al pulsarlo, vuelve al formulario de login y
descarta la elección en curso. Mientras se resuelve una elección, la pantalla queda deshabilitada
(no se puede elegir un segundo tenant ni repetir la misma elección con un doble click). Las cards son
operables por teclado/lector de pantalla (nombre accesible = nombre del tenant). Si el usuario recarga
la página estando en esta pantalla (no tiene ruta propia), la app degrada al formulario de login en
vez de romperse. Todo esto son hallazgos de `scenario-coverage`, incorporados sin discusión.

**Antes de escribir código**: ejecuta `npx shadcn add card` y revisa el diff de `package.json`. Si
añade alguna dependencia npm nueva, **PARA y pregunta al owner** qué paquete(s) trae y por qué antes
de dejar que `pnpm install` los instale — no lo asumas seguro (regla de honestidad del repo +
decisión explícita de `grilling`).

## Spec

`.claude/specs/frontend/casos-de-uso/CU-FE-01-login-y-sesion.md` (FR-028) — extensiones
1b/1c/1d/1e/1f.

## Fuera de alcance

- `auth-context.tsx` (ya completo en `-01`).
- `switchTenant`/switcher tras el login — tareas `-03`/`-04`.
- Nueva ruta/URL: descartado (el `identity_token` no debe viajar por URL/historial).

## Scenarios (Gherkin)

Fuente única (SDD): `CU-FE-01-login-y-sesion.md`. Esta tarea cubre, a nivel **RTL**
(`login-form.test.tsx` o un test dedicado del nuevo componente):

- `Login con 2+ tenants ofrece elegir uno` — tras un login con `LoginTenantSelection`, se muestran
  las cards (una por tenant, con su nombre) en vez de navegar.
- `Elegir un tenant completa la sesión` — al pulsar una card, navega a `/` (mismo comportamiento
  observable que el login single-tenant existente).
- `Error al elegir tenant permite reintentar sin volver a loguearse` — un error de `selectTenant`
  muestra una alerta (`role="alert"`) sobre la pantalla de cards, con el botón "Volver a iniciar
  sesión" visible **solo** en ese momento; elegir otra card (o la misma) reintenta sin pedir
  credenciales de nuevo.
- `Volver al login desde la pantalla de elección tras un error` — pulsar el botón vuelve al
  formulario de login (campos vacíos) y descarta la `identityToken`/lista en curso.
- `La pantalla de elección se deshabilita mientras resuelve` — con una elección en curso, las demás
  cards (y la misma) quedan deshabilitadas/no interactivas hasta que resuelve.
- `Recargar en la pantalla de elección degrada al login` — un remount de `login-form.tsx` sin el
  estado de selección en memoria (equivalente a una recarga) muestra el formulario de login, no un
  error ni una pantalla rota.

Accesibilidad (NFR-002, sin escenario Gherkin propio): cada card es un elemento operable por teclado
(rol de botón, nombre accesible = nombre del tenant) — verificado con `getByRole("button", { name })`
en el test RTL, no con selectores de implementación.

## Provides

- Componente de selección de tenant (cards), montado condicionalmente por `login-form.tsx`.

## Definition of Done

- [ ] Tests escritos ANTES de la implementación (TDD) — Red → Green → Refactor
- [ ] Cada escenario Gherkin tiene al menos un test (camino feliz + bordes/errores)
- [ ] Todos los tests en verde, incl. regresión de `login-form.test.tsx` (login single-tenant)
- [ ] Spec cumplida; lo declarado en `Provides` queda disponible para las dependientes
- [ ] Lint / format / typecheck OK
- [ ] Gate de mutation testing superado (Stryker, umbral `break: 80`)
- [ ] Gate de `sdd-lint` superado
- [ ] Gate de `fact-checker`: afirmaciones de la sesión verificadas (INCORRECTO bloquea)
- [ ] Documentación — TSDoc en símbolos públicos nuevos + session log; nota en el session log de si
  `shadcn add card` trajo dependencias nuevas y qué se decidió
