---
id: backend-routers-core-03
package: backend
plan: routers-core
status: pending
priority: 1
depends_on: []
estimate: 2h
actual:
issue:
created: 2026-08-19
updated: 2026-08-19
---

# Envelope de error (DomainError+Deny→problem+json) + schemas compartidos (Page[T], Problem)

## Description

Fundamento transversal que **todos** los routers de este plan necesitan: traducir cada excepción de
dominio (`app.domain.errors`) y cada `Deny` de `rbac_service` a `application/problem+json` (RFC 9457,
contrato), y los schemas Pydantic compartidos (`Page[T]` genérico, `Problem`) que todo router de listado
reutiliza. Sin dependencias de la identidad multi-tenant (01/02) — puede ejecutarse en paralelo con ellas.
Spec: `api-contract.yaml` (`Problem`, `Page`), CU-BE-03 (RN de `Deny`).

## Spec

- **Exception handlers** (`app/main.py` o módulo dedicado `app/api/errors.py` importado por
  `create_app()`): un handler por clase de `app.domain.errors`:
  - `NotFound` → 404, `Conflict`/`InvalidTransition` → 409, `Validation` → 422, `PortError` → 502 (fallo
    de un proveedor externo — no es culpa del cliente, tampoco 500 genérico).
  - Un handler para `Deny` de `rbac_service` (no es una excepción — el router que llama a `authorize()` y
    recibe `Deny` debe poder convertirlo en una respuesta HTTP sin un `if` ad-hoc por router): helper
    `deny_to_response(deny: Deny) -> NoReturn` (lanza una excepción HTTP interna) o un tipo de excepción
    `AuthorizationDenied(deny)` que el handler central traduce: `no_capability`→403, `out_of_scope`→404.
  - Fallback genérico para `Exception` no contemplada → 500 `problem+json`, **sin** filtrar detalles
    internos (mensaje genérico, `detail` no expone el traceback).
  - Todos los `Problem` respetan el shape del contrato (`type`, `title`, `status`, `detail`, `instance`
    opcional, `errors[]` opcional) y la localización `Accept-Language` (es/en) ya existente en `main.py`
    para 404/405/422/500/503 — se extiende el mismo mecanismo a estas 5 excepciones + `Deny`.
- **`app/api/v1/schemas/common.py`** (nuevo): `Page[T]` (genérico Pydantic, `items: list[T]`, `page: int`,
  `page_size: int`, `total: int`) + re-export de `Problem` si no vive ya en un módulo compartido.
- Sin lógica de negocio: este módulo **no** decide capacidades ni transiciones, solo traduce.

## Fuera de alcance

- Los routers que consumen este envelope (auth/tickets/messages/admin/kb) → tareas 05-09.
- `deps.get_current_subject`/`get_tenant_context`/`require_capability` → tarea 05.
- OpenAPI gate automatizado "generado ⊇ contrato" → tarea 19.

## Scenarios (Gherkin)

<!-- SDD: envelope de error transversal, sin CU propio — Gherkin LOCAL, "sin cambios de spec/CU" (no
     introduce comportamiento de negocio, traduce excepciones ya especificadas en cada CU). -->

```gherkin
Feature: envelope de error problem+json para toda la API

  Scenario Outline: cada DomainError se traduce al status correcto
    Given un endpoint que lanza <excepcion>
    When se hace la petición
    Then la respuesta es application/problem+json con status <status>

    Examples:
      | excepcion         | status |
      | NotFound          | 404    |
      | Conflict          | 409    |
      | InvalidTransition | 409    |
      | Validation        | 422    |
      | PortError         | 502    |

  Scenario: Deny(no_capability) se traduce a 403
    Given un endpoint protegido por una capacidad que el subject no tiene
    When se hace la petición
    Then la respuesta es 403 problem+json

  Scenario: Deny(out_of_scope) se traduce a 404
    Given un endpoint donde authorize() devuelve Deny(out_of_scope)
    When se hace la petición
    Then la respuesta es 404 problem+json (no revela que el recurso existe en otro tenant)

  Scenario: una excepción no contemplada da 500 sin filtrar detalles internos
    Given un endpoint que lanza una excepción de Python no mapeada
    When se hace la petición
    Then la respuesta es 500 problem+json con un detail genérico, sin traza ni mensaje interno

  Scenario: el Problem respeta Accept-Language
    Given un cliente que envía Accept-Language: en
    When ocurre un error mapeado (p.ej. NotFound)
    Then title/detail están en inglés

  Scenario: un Accept-Language no soportado cae al idioma por defecto
    Given un cliente que envía Accept-Language: fr (o un valor corrupto)
    When ocurre un error mapeado
    Then title/detail están en el idioma por defecto (es), sin fallar

  Scenario: los details de una Validation se vuelcan en Problem.errors[]
    Given una Validation con details={field: "priority", message: "valor inválido"}
    When se traduce al envelope
    Then Problem.errors[] contiene esa entrada, y Problem.detail no expone nada más allá de eso

  Scenario: Page[T] serializa items/page/page_size/total
    Given una lista de 3 elementos con page=1, page_size=20
    When se construye un Page con esos datos
    Then el JSON resultante tiene exactamente esas 4 claves con esos valores
```

## Provides

Exception handlers centrales registrados en `create_app()` (o importables desde `app.api.errors`);
`AuthorizationDenied`/`deny_to_response` helper para que cualquier router traduzca un `Deny` sin lógica
propia; `app.api.v1.schemas.common.Page[T]`. Consumido por **todos** los routers de este plan (05-09).

## Definition of Done

- [ ] Tests escritos ANTES de la implementación (Red → Green → Refactor).
- [ ] Cada escenario tiene al menos un test (nivel integración: cliente HTTP de FastAPI contra un endpoint
  de prueba mínimo que lanza cada excepción a propósito).
- [ ] Todos los tests en verde (`make test`).
- [ ] `Provides` disponible.
- [ ] `ruff check` (+`S`) + `ruff format --check` + `mypy` strict OK.
- [ ] Gate de mutation `cosmic-ray` (`break: 80`) sobre el módulo de handlers.
- [ ] Gate `/sdd-lint`: N/A (sin cambios de spec/CU, declarado en Scenarios).
- [ ] Gate de `fact-checker`.
- [ ] Documentación: docstrings (por qué `PortError`→502 y no 500, por qué `Deny` necesita un tipo propio
  en vez de mapear directo); session log.
