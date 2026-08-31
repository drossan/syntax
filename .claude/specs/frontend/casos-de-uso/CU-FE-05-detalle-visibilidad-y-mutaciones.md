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
- **1a.** Contenido de mensaje/adjunto con marcado peligroso (script/HTML crudo): se renderiza como
  **texto inerte** (anti-XSS) — nunca se ejecuta ni se inyecta como HTML.
- **1c.** (Ampliado, plan `frontend/markdown-rendering`,
  [[../../adr/0020-renderizado-markdown-seguro-con-allow-list]]) El cuerpo del mensaje contiene
  sintaxis Markdown legítima (negrita, listas, tablas, encabezados, imágenes, enlaces): se renderiza
  **formateado** (no literal), vía un allow-list explícito de elementos — sin distinguir si el
  mensaje lo escribió la IA o un humano (un solo camino de render para todos los mensajes del hilo).
  Una imagen embebida se carga con `referrerPolicy="no-referrer"` (evita filtrar en qué ticket está
  el usuario al servidor de esa imagen).
- **2b.** Acción destructiva (cerrar ticket): pide **confirmación** antes de ejecutar.
- **1b.** Adjuntos: **solo lectura** (sin subida en Fase 1).

## Reglas de negocio

- **RN-1** — Mutaciones idempotentes: optimistic + rollback por envelope; el resto, invalidación.
- **RN-2** — El filtro de visibilidad es defensa en profundidad (el backend también lo aplica).
- **RN-3** (FR-029, plan `frontend/markdown-rendering`) — El renderizado Markdown de un mensaje
  aplica por igual a TODOS los mensajes del hilo, sin condicionar a `is_ai_draft`. **Riesgo aceptado,
  sin mitigar** (`design-review` del plan, 2026-08-31): un mensaje humano con guiones/asteriscos
  casuales sin intención de formato se reinterpreta como Markdown; no se distingue autor.

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

  Scenario: Markdown legítimo se renderiza formateado
    Given un mensaje cuyo cuerpo contiene negrita y una lista en Markdown
    When se renderiza el hilo del ticket
    Then el mensaje se muestra formateado, no como texto literal

  Scenario: El renderizado no distingue autor
    Given un mensaje escrito por un humano con sintaxis Markdown
    When se renderiza el hilo del ticket
    Then se formatea igual que un mensaje generado por la IA

  Scenario: Una imagen embebida no filtra en qué ticket está el usuario
    Given un mensaje cuyo cuerpo contiene una imagen Markdown
    When se renderiza el hilo del ticket
    Then la imagen se carga sin enviar el `Referer` al servidor externo

  Scenario: Un mensaje sin cuerpo no rompe el render del hilo
    Given un mensaje cuyo cuerpo llega vacío o ausente
    When se renderiza el hilo del ticket
    Then el hilo se muestra sin que el render falle

  Scenario: Un mensaje humano con caracteres Markdown casuales se sigue leyendo razonablemente
    Given un mensaje escrito por un humano con guiones o asteriscos sin intención de dar formato
    When se renderiza el hilo del ticket
    Then el mensaje se sigue pudiendo leer con sentido, aunque se reinterprete como Markdown
```
