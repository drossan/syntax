# CU-FE-06 — Flujo IA: cola, ciclo de draft y decisiones

> **SDD** (Cockburn + Gherkin). CÓMO para FR-018…FR-020 de [`../spec.md`](../spec.md). Decisiones:
> [[../../adr/0011-entrega-draft-por-polling-no-sse-fase-1]], [[../../adr/0007-hitl-asincrono-postgressaver-checkpointer]].
> Backend: [CU-BE-06](../../backend/casos-de-uso/CU-BE-06-draft-ia-y-aprobacion-hitl.md).

- **Ámbito**: frontend (feature flujo-IA)
- **Nivel**: objetivo de usuario (Soporte)
- **Actor primario**: agente de Soporte
- **Interesados e intereses**:
  - Soporte — priorizar la cola y decidir cada borrador con contexto (confianza, fuentes).
  - Cliente — recibir solo respuestas aprobadas.

## Precondiciones

- El sujeto tiene `approval.decide` (decidir) y/o `agent.trigger` (disparar draft).

## Garantía mínima

- Ninguna decisión se envía dos veces; un run fallido se comunica y permite reintento.

## Garantía de éxito (postcondición)

- El borrador queda aprobado/editado/rechazado; el cliente recibe la respuesta solo si se aprobó/editó.

## Disparador

- El agente abre la cola, dispara un draft o decide sobre uno.

## Escenario principal (éxito)

1. La app muestra la **cola de aprobaciones** ordenada por SLA/confianza.
2. El agente dispara un draft; la app hace **polling** de `GET /agent-runs` mostrando el progreso.
3. El run termina `succeeded`; se muestra el borrador con confianza y fuentes.
4. El agente **aprueba/edita/rechaza** con nota-al-humano.

## Extensiones (flujos alternativos y de error)

- **2a.** El run termina `failed`: se muestra el error y se ofrece **reintento**.
- **4a.** **Rechazar**: pide **confirmación** (acción destructiva).
- **4b.** Segunda decisión sobre una tarea ya decidida (409): la app reconcilia sin duplicar (refresca la cola).

## Reglas de negocio

- **RN-1** — La entrega del draft es por polling (no SSE en Fase 1).
- **RN-2** — El polling se detiene al desmontar/hacer logout.

## Criterios de aceptación (Gherkin)

```gherkin
Feature: Flujo IA — cola, draft y decisiones

  Scenario: Cola ordenada por SLA y confianza
    Given varias tareas de aprobación pendientes
    When el agente abre la cola de aprobaciones
    Then las tareas se muestran ordenadas por SLA y confianza

  Scenario: Ciclo de draft por polling
    Given un agente que dispara la generación de un borrador
    When el borrador se está generando
    Then la interfaz refleja el progreso hasta que el run termina

  Scenario: Reintento ante run fallido
    Given un run de borrador que termina en fallo
    When se recibe el estado fallido
    Then se muestra el error y se ofrece reintentar la generación

  Scenario: Aprobación de un borrador
    Given un borrador generado con sus fuentes y confianza
    When el agente lo aprueba
    Then la respuesta queda aprobada y sale de la cola

  Scenario: Confirmación al rechazar
    Given un borrador pendiente
    When el agente intenta rechazar el borrador
    Then se le pide confirmación antes de rechazarlo

  Scenario: Decisión duplicada se reconcilia
    Given una tarea de aprobación que ya fue decidida en otra sesión
    When el agente intenta decidirla de nuevo y la API responde con conflicto
    Then la cola se refresca sin duplicar la respuesta
```
