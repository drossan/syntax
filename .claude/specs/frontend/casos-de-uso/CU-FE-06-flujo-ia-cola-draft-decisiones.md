# CU-FE-06 — Flujo IA: cola, ciclo de draft y decisiones

> **SDD** (Cockburn + Gherkin). CÓMO para FR-018…FR-020, FR-029 de [`../spec.md`](../spec.md). Decisiones:
> [[../../adr/0011-entrega-draft-por-polling-no-sse-fase-1]], [[../../adr/0007-hitl-asincrono-postgressaver-checkpointer]],
> [[../../adr/0019-auto-respuesta-resuelve-ticket-y-capacidad-ticket-reopen]].
> Backend: [CU-BE-06](../../backend/casos-de-uso/CU-BE-06-draft-ia-y-aprobacion-hitl.md).

- **Ámbito**: frontend (feature flujo-IA)
- **Nivel**: objetivo de usuario (Soporte; el escenario de auto-respuesta es del cliente, ver
  extensión 5a)
- **Actor primario**: agente de Soporte (camino HITL); el cliente que abrió el ticket (camino auto)
- **Interesados e intereses**:
  - Soporte — priorizar la cola y decidir cada borrador con contexto (confianza, fuentes).
  - Cliente — recibir solo respuestas aprobadas, o ver la auto-respuesta al momento cuando la
    confianza es suficiente y no hace falta revisión humana.

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
- **5a.** (Ampliado, plan `frontend/ticket-thread-live-refresh`,
  [[../../adr/0019-auto-respuesta-resuelve-ticket-y-capacidad-ticket-reopen]]) Camino **auto**
  (backend, `CU-BE-06` extensión 4c): el cliente que abrió el ticket ve el `AiDraftPanel` (sin
  gating de capacidad para la parte de estado, solo el botón de generar requiere `agent.trigger`) y
  su polling ya en marcha (`useAgentRun`) detecta la transición a `succeeded`. En ese momento, la
  app invalida la caché del ticket (mensajes + cabecera) — el hilo muestra la respuesta y la
  cabecera el `status` actualizado, **sin que el usuario recargue ni interactúe**.
- **5b.** El run del camino auto termina en `escalated` (pasa a HITL) o `failed`: **no** se dispara
  la invalidación de 5a — ese camino no publica mensaje hasta que un humano decide (4a-4b), momento
  en el que la decisión ya invalida la caché del ticket por su propio flujo.
- **5c.** (Ampliado, `scenario-coverage`) El panel se monta cuando el run **ya** está en `succeeded`
  (p.ej. el cliente vuelve a esta pestaña o navega de nuevo al detalle, no observa la transición en
  vivo): no se dispara una invalidación por cada montaje — solo una transición real desde otro
  estado a `succeeded` invalida.
- **5d.** (Ampliado, `scenario-coverage`) El `ticketId` cambia sin desmontar el panel (navegación
  entre tickets sin recargar): la comparación de estado anterior se resetea para el ticket nuevo, de
  modo que una transición real a `succeeded` en el ticket B se detecta igual que en el A.
- **5e.** (Ampliado, `scenario-coverage`) Tras un run que terminó en `failed`, el agente reintenta
  (dispara un segundo run): si ese segundo run llega a `succeeded`, la invalidación se dispara igual
  que en el primer ciclo — no depende de un flag de "ya invalidé una vez".

## Reglas de negocio

- **RN-1** — La entrega del draft es por polling (no SSE en Fase 1).
- **RN-2** — El polling se detiene al desmontar/hacer logout.
- **RN-3** (FR-029) — La invalidación de caché tras `succeeded` reutiliza el patrón ya existente de
  `invalidateQueries({ queryKey: ["ticket"] })` (mismo prefijo que ya usa la decisión de aprobación,
  `use-approval-decision.ts`) — no una key precisa por tenant+ticket ni un sondeo nuevo del hilo.
- **RN-4** (FR-029) — Solo la transición a `succeeded` dispara la invalidación; `escalated`/`failed`
  no la disparan (ver 5b).
- **RN-5** (FR-029, `scenario-coverage`) — La detección de "transición a succeeded" compara el
  estado anterior con el actual (vía `ref`) dentro de un `useEffect` — nunca en el cuerpo del
  render (`invalidateQueries` es un efecto colateral externo; ejecutarlo en render violaría la
  pureza de render y se duplicaría bajo StrictMode). Un montaje con el run ya en `succeeded` no
  cuenta como transición (5c); el `ticketId` resetea la comparación al cambiar (5d).

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

  Scenario: El cliente ve la auto-respuesta sin recargar
    Given un cliente con el detalle de su ticket abierto y un run del camino auto en curso
    When el run llega a succeeded
    Then el hilo de mensajes y la cabecera del ticket se refrescan solos

  Scenario: Un run escalado a HITL no refresca el hilo todavía
    Given un cliente con el detalle de su ticket abierto y un run que escala a revisión humana
    When el run pasa a estado de espera de aprobación
    Then el hilo de mensajes no se refresca hasta que un agente decida

  Scenario: Un run fallido no refresca el hilo
    Given un cliente con el detalle de su ticket abierto y un run que falla
    When el run termina en failed
    Then el hilo de mensajes no se refresca

  Scenario: Montar el panel con el run ya succeeded no invalida por sí solo
    Given un cliente que abre el detalle de un ticket cuyo run del camino auto ya está succeeded
    When el panel se monta
    Then el hilo de mensajes no se invalida por el simple montaje

  Scenario: Cambiar de ticket sin desmontar resetea la detección de transición
    Given un panel montado para un ticket A cuyo run ya terminó en succeeded
    When el cliente navega a un ticket B sin recargar y el run de B llega a succeeded
    Then el hilo de mensajes se invalida para la transición de B

  Scenario: Reintento tras fallo vuelve a disparar la invalidación
    Given un primer run que terminó en failed y el agente reintenta la generación
    When el segundo run llega a succeeded
    Then el hilo de mensajes y la cabecera del ticket se refrescan solos
```
