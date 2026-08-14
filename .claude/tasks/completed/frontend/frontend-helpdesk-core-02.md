---
id: frontend-helpdesk-core-02
package: frontend
plan: helpdesk-core
status: done
priority: 1
depends_on: [frontend-helpdesk-core-01, backend-skeleton-foundation-06]
estimate: 4h
actual: 5h
issue:
created: 2026-08-11
updated: 2026-08-13
---

# Cliente API tipado + mocks MSW + util de errores (contrato mecánico)

## Description

La capa que hace del contrato una **fuente de verdad mecánica** (design-review C1): genera tipos desde el
OpenAPI, valida los handlers MSW contra el schema, provee el cliente HTTP tipado con manejo de 401/429, y
la utilidad compartida que mapea el envelope `problem+json` a UI. **Precondición dura**: `backend-06`
entrega OpenAPI 3.1 real.

## Spec

- **Codegen** de tipos con `openapi-typescript` desde `api-contract` (script `pnpm gen:api`).
- **MSW** handlers **validados contra el schema** (openapi-msw o validación propia); fixtures por recurso.
- **Cliente HTTP** tipado (fetch/axios) con: header `Authorization: Bearer`; interceptor 401 (hook a 03);
  manejo de **429** (backoff/aviso, B.1).
- **Util `problemToUi(error)`** → `{ toast: {title, detail}, fieldErrors: Record<path,msg> }` con i18n
  (`errors[]` del envelope → errores de campo RHF).
- **Gate de conformidad**: script que regenera tipos+valida mocks; CI falla si hay drift con el contrato.

## Fuera de alcance

- Componentes de feature; auth (03) usa este cliente. Backend real.

## Scenarios (Gherkin)

```gherkin
Feature: Contrato de API mecánico y manejo de errores

  Scenario: Los tipos se generan desde el contrato
    Given un contrato OpenAPI 3.1 válido
    When se regeneran los tipos de la API
    Then existen tipos para cada recurso y el gate de conformidad pasa

  Scenario: Un mock MSW que no cumple el schema falla la validación
    Given un handler MSW cuya respuesta no cumple el schema del contrato
    When se ejecuta la validación de mocks
    Then el gate de conformidad falla señalando el recurso divergente

  Scenario: Un envelope de error se traduce a errores de campo y toast
    Given una respuesta problem+json con un `errors[]` sobre el campo "email"
    When el cliente procesa la respuesta de error
    Then `problemToUi` devuelve un fieldError para "email" y un toast localizado

  Scenario Outline: Respuesta del cliente según el status
    Given una petición autenticada
    When la API responde <status>
    Then el cliente <resultado>

    Examples:
      | status | resultado                                        |
      | 200    | resuelve con datos tipados                       |
      | 401    | dispara el flujo de refresh (una vez)            |
      | 429    | aplica backoff y expone un aviso de rate-limit   |
      | 422    | devuelve fieldErrors mapeados del envelope       |
```

## Provides

- `src/lib/api/` (cliente tipado), `src/types/api` (generados), `src/mocks/` (MSW validado),
  `problemToUi`. Toda tarea que hable con la API consume esto; el error→UI es transversal.

## Definition of Done

- [x] Tests escritos ANTES (TDD); cada escenario con ≥1 test (feliz + 401/429/422). 28 tests verdes.
- [x] Codegen + validación de mocks + gate de conformidad operativos; sin drift con el contrato (`gen:api:check` exit 0).
- [x] `pnpm --filter frontend lint` + typecheck OK; gate de mutation (92.13% ≥ break 80).
- [x] `Provides` disponible; gate de `fact-checker` (defecto del gate cazado y corregido); docs 3 capas + session log.
