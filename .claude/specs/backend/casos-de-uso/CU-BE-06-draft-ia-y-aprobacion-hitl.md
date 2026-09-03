# CU-BE-06 — Draft IA y aprobación HITL

> **SDD** (Cockburn + Gherkin). CÓMO para FR-022, FR-026…FR-031, FR-040, FR-057…FR-059 de
> [`../spec.md`](../spec.md). **Núcleo de riesgo**. Decisiones:
> [[../../adr/0007-hitl-asincrono-postgressaver-checkpointer]] ·
> [[../../adr/0022-auto-respuesta-resuelve-ticket-y-capacidad-ticket-reopen]]. Detalle:
> [`../agent-graph.md`](../agent-graph.md) §6.

- **Ámbito**: backend (grafo + checkpointer + servicio de aprobación)
- **Nivel**: objetivo de usuario (Soporte)
- **Actor primario**: agente de Soporte (decisor); el agente LangGraph produce el borrador
- **Interesados e intereses**:
  - Soporte — revisar y decidir cada respuesta antes de que llegue al cliente.
  - Cliente — recibir solo respuestas aprobadas por un humano.
  - Plataforma — durabilidad ante reinicios; idempotencia ante doble decisión.

## Precondiciones

- Hay contexto recuperado y una señal de confianza ([CU-BE-05](./CU-BE-05-clasificacion-y-retrieval-rag.md)).
- `auto_approve=false` para el tenant (Fase 1 por defecto).

## Garantía mínima

- Ningún mensaje `public` se emite sin una decisión `approved`/`edited`; un run fallido deja el sistema consistente.

## Garantía de éxito (postcondición)

- La decisión transiciona la `approval_task` y, salvo `rejected`, emite un `message` `public`; el `agent_run` cierra.

## Disparador

- `decide.requires_approval=true` en el run, o llega `approval.decide`.
- **Ampliado (tarea 12, routers flujo-IA)**: `POST /tickets/{id}/ai-draft` (capacidad `agent.trigger`) —
  el disparo HTTP que arranca el run que, más adelante, puede llegar a `decide.requires_approval=true`.
  Con el grafo real aún sin existir (15/16), el `AgentRun` creado por este disparo queda `queued` sin
  progresar — limitación conocida y documentada en el plan `routers-flujo-ia`.
- **Ampliado (`tenant.ai_auto_draft`, default `true`)**: `POST /tickets` dispara `agent.trigger`
  automáticamente justo tras crear el ticket (mismo `agent_service.trigger()`, sin puerto nuevo) — si
  el admin del tenant lo desactiva (`PATCH /tenants/settings`), el disparo vuelve a ser manual
  (`POST /tickets/{id}/ai-draft`). Best-effort: un fallo del disparo automático (rate-limit del
  tenant, proveedor caído) se loguea y NUNCA tumba la creación del ticket ya confirmada — el agente de
  soporte siempre puede disparar el draft a mano después. El ticket recién creado está en `new`, no
  `open` (nadie lo ha "tomado" todavía) — `decide()` en `approval_service.py` encadena `new/reopened
  →open→pending` en vez de saltar directo a `pending` (que no es una arista válida de CU-BE-04),
  preservando la máquina de estados sin necesitar que un humano abra el ticket a mano primero.

## Escenario principal (éxito)

1. El grafo llega a `decide` con `requires_approval=true`; llama a `interrupt()` (checkpoint Postgres) y crea `approval_task(pending)` con `draft_body`.
2. El agente de Soporte revisa el borrador en la cola.
3. Decide `approved`; el sistema reanuda con `Command(resume=approved)`.
4. `respond` emite un `message` `public` con `draft_body`; `approval_task→approved`, `agent_run→succeeded`.

## Extensiones (flujos alternativos y de error)

- **3a.** `edited`: se emite el `final_body` editado (se guarda en `approval_task.final_body`).
- **3b.** `rejected`: **no** se emite mensaje público; el run cierra superado; se conserva `human_note`.
- **3c.** Segunda `approval.decide` sobre la misma tarea ya decidida: el sistema responde **409** y **no** reanuda otra vez.
- **1a.** El proceso se reinicia entre el interrupt y la decisión: al llegar `resume`, el grafo **reanuda desde el checkpoint** (no re-ejecuta nodos completados).
- **1b.** Un nodo (p.ej. `generate`) falla: `agent_run→failed` con `error`; no queda `approval_task` si no se interrumpió.
- **0a.** (Ampliado, tarea 12) Ya hay un `AgentRun` no-terminal (`queued`/`running`) para el ticket: el
  disparo se rechaza con **409**, no se crea un segundo run — la garantía atómica real vive en el
  índice único parcial de `agent_run`, no solo en un chequeo previo.
- **0b.** (Ampliado, tarea 12) El tenant excede `ai_draft_rate_limit_per_minute` en la ventana actual:
  el disparo se rechaza con **429**, no se crea ningún `AgentRun` (rate-limiting mínimo in-memory por
  proceso — limitación multi-proceso documentada, no resuelta en esta tarea).
- **4c.** (Ampliado, plan `backend/auto-resolve-ticket`, [[../../adr/0022-auto-respuesta-resuelve-ticket-y-capacidad-ticket-reopen]])
  Camino **auto** (`decide.requires_approval=false`, sin HITL): antes de publicar el `message`,
  `respond` encadena la transición del ticket hasta `resolved` — recorre `_VALID_TRANSITIONS` desde
  el estado ACTUAL (nunca fuerza saltos que no apliquen): desde `new`/`reopened`,
  `→open→pending→resolved`; desde `open`, `→pending→resolved`; desde `pending`, `→resolved` directo.
  Si un salto intermedio falla, **no** se publica el mensaje (transición-antes-que-publicación: más
  seguro dejar sin responder que publicar sobre un ticket en estado a medias). Cada salto genera su
  entrada normal de audit log (`ticket.transitioned`, con `actor_id=None` explícito — "sistema", no
  un `Subject` humano), sin marca especial.
- **4d.** El ticket YA está en `resolved`/`closed` cuando el camino auto llega a publicar (p.ej. un
  `agent.trigger` manual disparado después de que el ticket ya se resolvió): **no** se intenta
  ninguna transición — se publica el mensaje igual, dejando el estado como estaba.
- **4e.** El cliente considera que la auto-respuesta no vale: con la capacidad `ticket.reopen`
  (nueva, distinta y más estrecha que `ticket.transition` — habilita únicamente
  `{resolved,closed}→reopened`), reabre el ticket vía el endpoint dedicado, desde `resolved` o desde
  `closed`. Un sujeto sin `ticket.reopen` (o intentando cualquier otro destino) recibe **403**.
- **4f.** (Ampliado, `scenario-coverage`) Un sujeto con `ticket.reopen` intenta reabrir un ticket que
  **no** está en `resolved`/`closed` (p.ej. `new`, `open`, `pending`, `reopened`): el sistema
  responde **409** (`InvalidTransition`) — distinto del 403 de 4e: aquí la capacidad SÍ está
  presente, es el estado del ticket el que no admite la transición.
- **4g.** (Ampliado, `scenario-coverage`) El ticket a reabrir pertenece a **otro tenant**: invisible
  por el aislamiento app-level/RLS ya establecido (mismo criterio que el resto de endpoints de
  ticket) — **404**, nunca 200 ni 403 (no revela que el ticket existe en otro tenant). Un `id`
  inexistente da el mismo 404.

## Reglas de negocio

- **RN-1** — `thread_id = ticket_{id}_run_{n}` es el punto de serialización del run (una sola reanudación).
- **RN-2** — Decidir una `approval_task` no-`pending` es no-op idempotente (409 en carrera).
- **RN-3** — El contenido del ticket es input no confiable: aislado del system-prompt, sin ejecutar instrucciones embebidas.
- **RN-4** (FR-040) — Un ticket con un `agent_run` no-terminal (`queued`/`running`) no admite un segundo disparo: la garantía atómica real vive en el índice único parcial de `agent_run`, el pre-check previo es solo optimización.
- **RN-5** (FR-040) — El disparo de `ai-draft` está acotado por un límite de tasa por tenant y ventana; excederlo rechaza el disparo sin crear ningún `agent_run` (rate-limiting in-memory por proceso, limitación multi-proceso documentada y no resuelta).
- **RN-6** (FR-057) — El camino auto transiciona el ticket **antes** de publicar el mensaje; un fallo de transición aborta la publicación (nunca publica sobre un estado a medias).
- **RN-7** (FR-057) — El encadenado hacia `resolved` parte del estado ACTUAL del ticket y solo recorre aristas ya válidas de `_VALID_TRANSITIONS` (CU-BE-04) — nunca fuerza un salto no cubierto por la máquina de estados.
- **RN-8** (FR-059) — Si el ticket ya está en `resolved`/`closed` cuando el camino auto publica, no se intenta ninguna transición.
- **RN-9** (FR-058) — `ticket.reopen` es una capacidad distinta de `ticket.transition`, acotada por el servicio a `{resolved,closed}→reopened` exclusivamente — ningún otro destino es alcanzable con ella.
- **RN-11** (FR-058, `scenario-coverage`) — Reabrir un ticket que no está en `{resolved,closed}` con la capacidad presente es **409**, no 403 — el 403 es exclusivo de la ausencia de capacidad; el 409 es exclusivo de un estado de origen inválido.
- **RN-12** (FR-058, `scenario-coverage`) — El aislamiento cross-tenant de `ticket.reopen` sigue el mismo criterio que el resto de endpoints de ticket: un ticket de otro tenant (o inexistente) da 404, nunca 403 ni 200.
- **RN-10** (FR-057, asimetría aceptada — [[../../adr/0022-auto-respuesta-resuelve-ticket-y-capacidad-ticket-reopen]]) — El camino auto (sin revisión humana) llega a `resolved`; el camino HITL aprobado se detiene en `pending` (RN existente de `approval_service.decide()`). Es una consecuencia conocida y aceptada de la decisión de diseño, no un error a corregir en esta capa.

## Criterios de aceptación (Gherkin)

```gherkin
Feature: Draft IA y aprobación HITL

  Scenario: Aprobación emite la respuesta al cliente
    Given un borrador IA pendiente de aprobación para un ticket
    When un agente de Soporte lo aprueba
    Then se publica un mensaje público con el borrador y la tarea de aprobación queda aprobada

  Scenario: Edición envía el texto corregido
    Given un borrador IA pendiente de aprobación
    When un agente lo edita y lo aprueba
    Then se publica el texto editado y se conserva como respuesta final

  Scenario: Rechazo no publica nada al cliente
    Given un borrador IA pendiente de aprobación
    When un agente lo rechaza con una nota
    Then no se publica ningún mensaje público y se conserva la nota al humano

  Scenario: Doble decisión es idempotente
    Given una tarea de aprobación que ya ha sido decidida
    When llega una segunda decisión sobre la misma tarea
    Then el sistema responde 409 y no reanuda el run por segunda vez

  Scenario: Reinicio a mitad de run reanuda desde el checkpoint
    Given un run interrumpido a la espera de aprobación y un proceso reiniciado
    When llega la decisión de aprobación
    Then el grafo reanuda desde el último checkpoint sin re-ejecutar los nodos ya completados

  Scenario: Fallo del LLM deja el sistema consistente
    Given un run en el que la generación del borrador falla
    When el nodo de generación devuelve un error
    Then el run queda marcado como fallido y no se crea ninguna tarea de aprobación

  Scenario: Disparar un draft con un run activo es un conflicto
    Given un ticket con un AgentRun en curso (queued o running)
    When se dispara un nuevo draft para ese ticket
    Then el sistema responde 409 y no crea un segundo AgentRun

  Scenario: Disparar por encima del límite de la ventana es rechazado
    Given un tenant que agotó su cuota de ai-draft en la ventana actual
    When dispara un nuevo draft
    Then el sistema responde 429 y no crea ningún AgentRun

  Scenario Outline: La auto-respuesta encadena hasta resolved desde cualquier estado de partida
    Given un ticket en estado <estado_inicial> con auto_approve activo y confianza suficiente
    When el grafo publica la respuesta por el camino auto
    Then el ticket queda en resolved y el mensaje se publica

    Examples:
      | estado_inicial |
      | new            |
      | reopened       |
      | open           |
      | pending        |

  Scenario: La auto-respuesta no publica si un salto de la transición falla
    Given un ticket cuya transición hacia resolved falla a mitad de camino
    When el grafo intenta publicar la respuesta por el camino auto
    Then no se publica ningún mensaje y el ticket no queda en un estado inconsistente

  Scenario: Auto-respuesta sobre un ticket ya resuelto no toca el estado
    Given un ticket ya en resolved o closed
    When el grafo publica una respuesta por el camino auto
    Then el mensaje se publica y el estado del ticket no cambia

  Scenario Outline: El cliente reabre un ticket auto-resuelto que no le vale
    Given un ticket <estado_inicial> que el agente respondió automáticamente
    When un sujeto con la capacidad ticket.reopen lo reabre
    Then el ticket queda en reopened

    Examples:
      | estado_inicial |
      | resolved       |
      | closed         |

  Scenario: Reabrir sin la capacidad adecuada se rechaza
    Given un ticket resolved y un sujeto sin la capacidad ticket.reopen
    When ese sujeto intenta reabrirlo
    Then el sistema responde 403 y el ticket no cambia de estado

  Scenario: ticket.reopen no habilita ninguna otra transición
    Given un sujeto que solo tiene la capacidad ticket.reopen
    When intenta transicionar un ticket a un destino distinto de reopened
    Then el sistema responde 403

  Scenario Outline: Reabrir un ticket que no está en un estado válido para ello es un conflicto
    Given un ticket <estado_inicial> y un sujeto con la capacidad ticket.reopen
    When ese sujeto intenta reabrirlo
    Then el sistema responde 409 y el ticket no cambia de estado

    Examples:
      | estado_inicial |
      | new            |
      | open           |
      | pending        |
      | reopened       |

  Scenario: Reabrir un ticket de otro tenant no revela que existe
    Given un ticket resolved perteneciente a otro tenant
    When un sujeto con ticket.reopen de un tenant distinto intenta reabrirlo
    Then el sistema responde 404

  Scenario: Reabrir un ticket inexistente da 404
    Given un id de ticket que no existe
    When un sujeto con ticket.reopen intenta reabrirlo
    Then el sistema responde 404
```
