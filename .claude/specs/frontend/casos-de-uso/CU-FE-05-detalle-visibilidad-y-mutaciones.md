# CU-FE-05 — Detalle, visibilidad y mutaciones del ticket

> **SDD** (Cockburn + Gherkin). CÓMO para FR-014…FR-017 de [`../spec.md`](../spec.md). Políticas:
> [`../cross-cutting.md`](../cross-cutting.md) §6 (concurrencia optimista), §1 (anti-XSS). Backend:
> [CU-BE-04](../../backend/casos-de-uso/CU-BE-04-ciclo-de-vida-del-ticket.md).

- **Ámbito**: frontend (feature tickets — detalle)
- **Nivel**: objetivo de usuario
- **Actor primario**: agente/usuario
- **Interesados e intereses**:
  - Agente — cambiar estado/prioridad/asignación con feedback inmediato y seguro.
  - Cliente — no ver notas `internal`.

## Precondiciones

- El sujeto tiene `ticket.read` sobre el ticket; para mutar, la capacidad correspondiente.

## Garantía mínima

- Una mutación fallida deja la vista **consistente** (rollback); el cliente nunca ve mensajes `internal`.

## Garantía de éxito (postcondición)

- El ticket refleja el cambio; el hilo muestra solo lo que corresponde a la visibilidad del sujeto.

## Disparador

- El usuario abre el detalle o muta estado/prioridad/asignación.

## Escenario principal (éxito)

1. La app muestra el hilo, filtrando `internal` según `note.internal.read`.
2. El agente cambia estado/prioridad/asignación → **optimistic-update** inmediato.
3. La API confirma; la caché se consolida.

## Extensiones (flujos alternativos y de error)

- **2a.** La API devuelve error/`409`: **rollback** al estado previo, consistente con la última acción real.
- **1a.** Contenido de mensaje/adjunto con marcado peligroso: se renderiza como **texto inerte** (anti-XSS).
- **2b.** Acción destructiva (cerrar ticket): pide **confirmación** antes de ejecutar.
- **1b.** Adjuntos: **solo lectura** (sin subida en Fase 1).

## Reglas de negocio

- **RN-1** — Mutaciones idempotentes: optimistic + rollback por envelope; el resto, invalidación.
- **RN-2** — El filtro de visibilidad es defensa en profundidad (el backend también lo aplica).

## Criterios de aceptación (Gherkin)

```gherkin
Feature: Detalle, visibilidad y mutaciones del ticket

  Scenario: El cliente no ve notas internas
    Given un usuario sin permiso de notas internas viendo un ticket con una nota interna
    When abre el detalle del ticket
    Then la nota interna no aparece en el hilo

  Scenario: Mutación optimista confirmada
    Given un agente en el detalle de un ticket
    When cambia el estado del ticket
    Then el cambio se refleja de inmediato y persiste tras completarse la operación

  Scenario: Rollback ante conflicto
    Given una mutación optimista de un ticket
    When la API responde con un conflicto
    Then la vista revierte al estado previo de forma consistente

  Scenario: Confirmación en acción destructiva
    Given un agente que va a cerrar un ticket
    When intenta cerrar el ticket
    Then se le pide confirmación antes de aplicar el cambio

  Scenario: Contenido externo se muestra como texto inerte
    Given un mensaje cuyo cuerpo contiene marcado tipo script
    When se renderiza el hilo del ticket
    Then el marcado se muestra como texto y no se ejecuta
```
