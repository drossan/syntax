---
id: frontend-helpdesk-core-08
package: frontend
plan: helpdesk-core
status: done
priority: 2
depends_on: [frontend-helpdesk-core-07]
estimate: 3h
actual: 1h
issue:
created: 2026-08-11
updated: 2026-08-13
---

# Alta de ticket

## Description

Formulario de creación de ticket (RHF+Zod): asunto, descripción, prioridad, dominio/categoría (17
dominios), adjuntos opcionales. Valida en cliente y mapea errores del envelope.

## Spec

- Form RHF+Zod (asunto requerido, descripción, prioridad, dominio); envío → `POST /tickets`.
- Éxito → navega al detalle del ticket creado. Error de validación del server → fieldErrors (`problemToUi`).
- El `tenant_id` se toma del contexto (cliente) o del tenant seleccionado (soporte).

## Fuera de alcance

- Subida real de adjuntos (view-only, 11). Clasificación IA (backend).

## Scenarios (Gherkin)

```gherkin
Feature: Alta de ticket

  Scenario: Creación válida
    Given una usuaria con capacidad para crear tickets
    When crea un ticket con asunto, descripción, prioridad y dominio válidos
    Then el ticket se crea y es llevada a su detalle

  Scenario: Validación en cliente
    Given el formulario de alta
    When intenta enviar sin asunto
    Then se muestra el error de campo requerido y no se envía

  Scenario: Error de validación del servidor
    Given un envío que el servidor rechaza con errores de campo
    When la API responde 422 con el envelope de error
    Then los errores se muestran en los campos correspondientes
```

## Provides

- Página/form de alta. Enlazado desde la bandeja (07).

## Definition of Done

- [x] Tests ANTES (TDD); cada escenario con ≥1 test (válido, validación cliente, 422 server).
- [x] Form RHF+Zod + mapeo de errores; `tenant_id` derivado server-side (contrato no lo pide en body). *(domain no va en `TicketCreate` — clasificación backend; gap documentado)*
- [x] Lint + typecheck OK; gate de mutation 100% (break 80); estados + a11y del form (`aria-invalid`, labels, `role=alert`).
- [x] `Provides` disponible (form + enlace desde bandeja); `fact-checker` 10/10 VERIFICADO; docs 3 capas + session log.
