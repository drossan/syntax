# 0004. Auth JWT: access en memoria + refresh en cookie httpOnly con rotación y reuse-detection

- **Estado**: accepted
- **Fecha**: 2026-08-11
- **Decisores**: Owner; `grilling` backend (rama 5) + refuerzos **A1.5/A1.7** de `scenario-coverage`.

## Contexto y planteamiento del problema

El helpdesk es multi-tenant con personal de Soporte cross-tenant: la sesión debe ser **segura**,
**revocable** y permitir **logout server-side**. Un cambio o revocación de rol debe surtir efecto pronto.
¿Cómo se estructuran los tokens y dónde se resuelven las capacidades?

## Decision drivers

- Minimizar superficie XSS (no token en `localStorage`) y CSRF.
- Revocación efectiva y **logout server-side**; detección de robo de refresh.
- Que un cambio de rol se refleje rápido sin invalidar todo a mano.

## Opciones consideradas

- **Opción 1** — **Access Bearer en memoria** (TTL corto, **sin capacidades en el JWT**) + **refresh en
  cookie httpOnly** con **rotación** (`family_id`) y **reuse-detection**; capacidades resueltas
  **server-side por request** desde la BD.
- **Opción 2** — Access de larga vida en `localStorage`, sin refresh rotatorio.
- **Opción 3** — Sesión server-side stateful pura (cookie de sesión opaca, sin JWT).

## Resultado de la decisión

Elegida: **Opción 1**. El access (memoria, TTL corto) porta identidad, **no** capacidades; el refresh vive
en cookie **httpOnly** y **rota** en cada uso (cadena `family_id`/`parent_id`); un refresh ya `rotated`/
`revoked` que reaparece dispara **reuse-detection** → se revoca **toda la familia** (logout global de esa
cadena). Las **capacidades se resuelven server-side por request** desde la BD (no desde el JWT): una
revocación de rol surte efecto en la siguiente request y el TTL corto acota la obsolescencia de pertenencia.

### Confirmación

`refresh_session` en `data-model.md` §4.1 (rotación/reuse-detection/logout); `app/core/security.py`
(guión: Argon2id, JWT sin capacidades, refresh contra `refresh_session`); interceptor 401 **single-flight**
+ reuse-detection→logout en el frontend (helpdesk-core, [[0003-frontend-spa-client-rendered]]).

## Consecuencias

- **Buenas**: revocación efectiva; robo de refresh detectable; capacidades siempre frescas.
- **Malas / coste**: token store (`refresh_session`) + lógica de rotación; N 401 concurrentes exigen
  **single-flight** en el cliente para una sola renovación.

## Pros y contras de las opciones

- **Opción 1**: 👍 seguro, revocable, capacidades frescas · 👎 más piezas (store + rotación).
- **Opción 2**: 👍 trivial · 👎 XSS-expuesto, no revocable, capacidades obsoletas.
- **Opción 3**: 👍 revocación simple · 👎 estado de sesión en cada request; menos encaje con SPA/API stateless.
