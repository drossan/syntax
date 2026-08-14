# CU-BE-06 — Draft IA y aprobación HITL

> **SDD** (Cockburn + Gherkin). CÓMO para FR-022, FR-026…FR-031 de [`../spec.md`](../spec.md). **Núcleo de
> riesgo**. Decisión: [[../../adr/0007-hitl-asincrono-postgressaver-checkpointer]]. Detalle:
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

## Reglas de negocio

- **RN-1** — `thread_id = ticket_{id}_run_{n}` es el punto de serialización del run (una sola reanudación).
- **RN-2** — Decidir una `approval_task` no-`pending` es no-op idempotente (409 en carrera).
- **RN-3** — El contenido del ticket es input no confiable: aislado del system-prompt, sin ejecutar instrucciones embebidas.

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
```
