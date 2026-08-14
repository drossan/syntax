# 0003. Frontend SPA client-rendered con access token en memoria

- **Estado**: accepted
- **Fecha**: 2026-08-11
- **Decisores**: Owner; hallazgo **I1** de `design-review` (plan frontend).

## Contexto y planteamiento del problema

El access token vive **en memoria** (decisión de auth, [[0004-auth-jwt-access-memoria-refresh-cookie-rotacion]]):
no es legible por los **Server Components** de Next. ¿Dónde ocurre el data-fetching autenticado y qué papel
juega el `middleware.ts`? Una arquitectura mixta RSC/cliente para datos privados sería incoherente con un
token que el servidor no puede leer.

## Decision drivers

- El token no debe exponerse a Server Components ni persistirse en almacenamiento legible por XSS.
- Coherencia: dónde vive el token determina dónde se hacen las llamadas autenticadas.
- Evitar una capa BFF que reimplemente auth/routing sin aportar valor en Fase 1.

## Opciones consideradas

- **Opción 1** — App **client-rendered**: fetch autenticado client-side (TanStack Query + cliente tipado);
  RSC solo para *chrome* estático; `middleware.ts` = **redirect UX** por presencia de cookie refresh.
- **Opción 2** — **BFF de Next**: la SPA llama a route handlers de Next que proxyan a la API.
- **Opción 3** — **SSR** con el token en cookie legible por el servidor.

## Resultado de la decisión

Elegida: **Opción 1 (SPA client-rendered)**. Todo dato de servidor pasa por **TanStack Query + cliente
API tipado**; los Server Components se usan solo para chrome estático. El `middleware.ts` **solo ve la
cookie refresh** y hace **redirect de UX** — **no es control de seguridad**: la autorización real la hace
la API server-side (deny→403, reconciliado en cliente sin mutar estado).

### Confirmación

helpdesk-core I1; `middleware.ts` implementado como redirect por cookie; 297 tests unit/RTL/MSW verdes +
2 smokes e2e (2026-08-13). El BFF de Next quedó **descartado** explícitamente (SPA llama a la API directa).

## Consecuencias

- **Buenas**: el token nunca llega a RSC ni a storage persistente; arquitectura simple y coherente.
- **Malas / coste**: sin data-fetching en servidor (no SSR de datos privados); el cliente asume el trabajo
  de caché/estado (mitigado con TanStack Query).

## Pros y contras de las opciones

- **Opción 1**: 👍 token seguro, coherente, sin BFF · 👎 sin SSR de datos.
- **Opción 2**: 👍 oculta la API, permite SSR · 👎 duplica auth/routing; superficie extra sin valor Fase 1.
- **Opción 3**: 👍 SSR real · 👎 token en cookie legible = mayor superficie XSS/CSRF.
