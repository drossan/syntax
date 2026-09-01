# CU-FE-05 — Detalle, visibilidad y mutaciones del ticket

> **SDD** (Cockburn + Gherkin). CÓMO para FR-014…FR-017 de [`../spec.md`](../spec.md). Políticas:
> [`../cross-cutting.md`](../cross-cutting.md) §6 (concurrencia optimista), §1 (anti-XSS). Backend:
> [CU-BE-04](../../backend/casos-de-uso/CU-BE-04-ciclo-de-vida-del-ticket.md). Renderizado:
> [ADR-0020](../../adr/0020-renderizado-markdown-seguro-con-allow-list.md); edición:
> [ADR-0021](../../adr/0021-editor-markdown-nativo-con-preview-reusando-el-allow-list.md).

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
- **1d.** (plan `frontend/markdown-editor`,
  [[../../adr/0021-editor-markdown-nativo-con-preview-reusando-el-allow-list]]) Responder al ticket
  usa `MarkdownEditor` (toolbar + preview) en vez de un `<textarea>` plano — la preview reusa el
  mismo allow-list de la extensión 1c, sin motor de renderizado adicional. La casilla de
  lista-de-tareas del toolbar (`- [ ] texto`) está excluida — no forma parte del allow-list de
  lectura, y dejarla produciría un texto que se ve distinto al escribirlo que al publicarse.

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

  Scenario: Responder al ticket usa el editor de Markdown en vez de texto plano
    Given el formulario de respuesta al ticket
    When el usuario usa el toolbar del editor para dar formato a la respuesta
    Then el campo de respuesta contiene el string de Markdown resultante

  Scenario: La casilla de lista-de-tareas no está disponible en el toolbar de respuesta
    Given el editor de respuesta al ticket
    When el usuario mira los comandos disponibles del toolbar
    Then no hay un comando que inserte una casilla de lista-de-tareas

  Scenario: El botón nativo de alternar modo de vista no está disponible
    Given el editor de respuesta al ticket
    When el usuario mira los comandos disponibles del toolbar
    Then no hay un botón para cambiar entre modo edición/preview/live — la vista previa queda fija,
      igual en las 3 superficies que la usan

  Scenario: El Markdown compuesto en el editor llega intacto a la publicación
    Given una respuesta compuesta con el editor de Markdown
    When el usuario envía el formulario de respuesta
    Then el mensaje se publica con el mismo string de Markdown que el editor mostraba

  Scenario: Una respuesta vacía sigue bloqueando el envío con el nuevo editor
    Given el editor de respuesta vacío
    When el usuario intenta enviar el formulario
    Then el envío se bloquea y el error de "mensaje obligatorio" se asocia al campo del editor

  Scenario: Marcado adversario tecleado directamente en el editor se previsualiza inerte
    Given el editor de respuesta con texto <script>window.__pwned = true;</script> pegado a mano
    When el usuario mira la vista previa del editor
    Then el script se muestra como texto, nunca se ejecuta

  Scenario Outline: Cada comando del toolbar produce Markdown que la preview renderiza formateado
    Given el editor de respuesta vacío
    When el usuario usa el comando <comando> del toolbar
    Then la vista previa muestra el resultado como <resultado>

    Examples:
      | comando          | resultado                      |
      | negrita          | texto en <strong>              |
      | cursiva          | texto en <em>                  |
      | tachado          | texto en <del>                 |
      | lista no ordenada| un <ul> con al menos un <li>    |
      | lista ordenada   | un <ol> con al menos un <li>    |
      | enlace           | un <a> con target/rel seguros   |
      | código           | un <code>                       |
      | cita             | un <blockquote>                 |
      | tabla            | una <table> con cabecera y filas|

  Scenario: El toolbar es operable por teclado
    Given el editor de respuesta al ticket
    When el usuario navega el toolbar con el teclado (sin ratón)
    Then cada comando es alcanzable y activable por teclado

  Scenario: Las etiquetas del toolbar cambian con el idioma activo
    Given el editor de respuesta al ticket con el idioma de la sesión en inglés
    When el usuario pasa el ratón sobre un comando del toolbar
    Then el tooltip se muestra en inglés, no en el idioma por defecto de la librería
```
