# CU-BE-04 — Ciclo de vida del ticket

> **SDD** (Cockburn + Gherkin). CÓMO para FR-016…FR-021 de [`../spec.md`](../spec.md). Estados/entidades:
> [`../data-model.md`](../data-model.md) (`ticket_status`, `message_visibility`). SLA:
> [CU-BE-08](./CU-BE-08-scheduler-de-sla.md).

- **Ámbito**: backend (servicios de dominio de ticket/message)
- **Nivel**: objetivo de usuario
- **Actor primario**: usuario/agente con capacidades de ticket
- **Interesados e intereses**:
  - Usuario — abrir y seguir el ticket hasta su resolución.
  - Agente — gestionar estado, asignación, prioridad y respuestas.
  - Plataforma — transiciones válidas y trazabilidad (auditoría).

## Precondiciones

- El sujeto tiene la capacidad correspondiente (`ticket.create/reply/transition/assign`) en el ámbito.

## Garantía mínima

- Una transición inválida no altera el estado del ticket; toda mutación aplicada queda auditada.

## Garantía de éxito (postcondición)

- El ticket refleja el nuevo estado/asignación/mensaje; el hilo mantiene el orden determinista.

## Disparador

- El sujeto crea, responde, transiciona o asigna un ticket.

## Escenario principal (éxito)

1. El usuario crea un ticket → estado `new` en su tenant. Si `tenant.ai_auto_draft` está activo
   (default `true`), esto además dispara `agent.trigger` automáticamente ([CU-BE-06](./CU-BE-06-draft-ia-y-aprobacion-hitl.md))
   — el ticket sigue en `new` (crear ≠ tomar), best-effort (un fallo del disparo IA no bloquea la
   creación).
2. El agente lo toma (`open`), responde (mensaje `public`) y ajusta prioridad/asignación.
3. El agente lo marca `resolved` y luego `closed`.
4. Cada mutación se registra en `audit_log`.

## Extensiones (flujos alternativos y de error)

- **2a.** Transición no válida en la máquina de estados: el sistema la rechaza (el estado no cambia).
- **2b.** Nota `internal`: solo visible para sujetos con `note.internal.read`.
- **3a.** El cliente reabre un ticket `closed` → `reopened` (habilita un nuevo run IA, [CU-BE-06](./CU-BE-06-draft-ia-y-aprobacion-hitl.md)).

## Reglas de negocio

- **RN-1** — Máquina de estados: `new→open→pending→resolved→closed→reopened` (transiciones válidas).
- **RN-2** — El hilo se ordena por `(ticket_id, created_at)` (determinista).
- **RN-3** — Borrar/anonimizar un usuario deja `SET NULL` en `requester_id`/`assignee_id` (el ticket sobrevive).

## Criterios de aceptación (Gherkin)

```gherkin
Feature: Ciclo de vida del ticket

  Scenario: Alta de un ticket
    Given un usuario con capacidad de crear tickets en su tenant
    When abre un ticket nuevo
    Then el ticket queda en estado "new" dentro de su tenant

  Scenario: Respuesta pública a un ticket
    Given un ticket abierto y un agente con capacidad de responder
    When el agente responde al ticket
    Then se registra un mensaje de visibilidad pública en el hilo

  Scenario: Nota interna oculta al cliente
    Given un ticket con una nota interna
    When un usuario sin permiso de notas internas consulta el hilo
    Then la nota interna no aparece en su vista

  Scenario: Transición inválida se rechaza
    Given un ticket en estado "new"
    When se intenta transicionarlo directamente a "closed" saltando la máquina de estados
    Then la transición se rechaza y el estado permanece "new"

  Scenario: Reapertura de un ticket cerrado
    Given un ticket en estado "closed"
    When el cliente lo reabre
    Then el ticket pasa a "reopened"

  Scenario: Toda mutación queda auditada
    Given un ticket existente
    When un agente cambia su estado o asignación
    Then la mutación queda registrada en el log de auditoría
```
