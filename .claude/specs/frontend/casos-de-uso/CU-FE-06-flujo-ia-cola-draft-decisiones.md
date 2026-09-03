# CU-FE-06 — Flujo IA: cola, ciclo de draft y decisiones

> **SDD** (Cockburn + Gherkin). CÓMO para FR-018…FR-020 de [`../spec.md`](../spec.md). Decisiones:
> [[../../adr/0011-entrega-draft-por-polling-no-sse-fase-1]], [[../../adr/0007-hitl-asincrono-postgressaver-checkpointer]],
> [[../../adr/0021-editor-markdown-nativo-con-preview-reusando-el-allow-list]] (edición del borrador).
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
- **3a.** (Ampliado, plan `frontend/markdown-rendering`,
  [[../../adr/0020-renderizado-markdown-seguro-con-allow-list]]) El borrador contiene sintaxis
  Markdown (negrita, listas, tablas, encabezados, imágenes): se muestra **formateado**, vía un
  allow-list explícito de elementos — nunca como texto literal ni como HTML crudo interpretado
  (`cross-cutting.md` §1, NFR-004).
- **3b.** (Ampliado, `design-review` del plan) El borrador contiene marcado adversario (script/HTML
  embebido): se muestra como **texto inerte**, nunca se ejecuta ni se inyecta como HTML.
- **3c.** (Ampliado, `design-review` del plan) El borrador llega **truncado a mitad de una sintaxis
  Markdown** (el backend trunca a un máximo de caracteres antes de anexar las fuentes): el
  renderizado no rompe — el contenido parcial se muestra, aunque la sintaxis cortada quede incompleta.
- **3d.** (Ampliado, `scenario-coverage` del plan) Un enlace del borrador se abre en pestaña nueva con
  `rel="noopener noreferrer"` — evita el vector de *reverse tabnabbing* sin arriesgar la sesión SPA.
  Un enlace/imagen con protocolo `javascript:` queda neutralizado (`react-markdown` lo sanea por
  defecto).
- **3e.** (Ampliado, `scenario-coverage` del plan) El borrador llega vacío o solo con espacios: el
  render no falla.
- **4a.** **Rechazar**: pide **confirmación** (acción destructiva).
- **4b.** Segunda decisión sobre una tarea ya decidida (409): la app reconcilia sin duplicar (refresca la cola).
- **4c.** (plan `frontend/markdown-editor`,
  [[../../adr/0021-editor-markdown-nativo-con-preview-reusando-el-allow-list]]) **Editar** un borrador
  antes de aprobar usa `MarkdownEditor` (toolbar + preview) en vez de un `<textarea>` plano — la
  preview reusa el mismo componente/allow-list de la extensión 3a (RN-3), garantizando que lo que se
  ve al editar es exactamente lo que se publicará.

## Reglas de negocio

- **RN-1** — La entrega del draft es por polling (no SSE en Fase 1).
- **RN-2** — El polling se detiene al desmontar/hacer logout.
- **RN-3** (plan `frontend/markdown-rendering`) — El renderizado del borrador comparte el mismo
  componente y allow-list que el resto de mensajes del hilo (FR-029, ver CU-FE-05 RN-3) — una sola
  fuente de verdad para "qué Markdown se permite", no una config duplicada por superficie.

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

  Scenario: El borrador con Markdown se muestra formateado
    Given un borrador con negrita, una lista y una sección de fuentes en Markdown
    When el agente revisa el borrador en la cola
    Then lo ve formateado (negrita, lista), no como texto literal

  Scenario: El borrador con marcado adversario se muestra inerte
    Given un borrador cuyo texto contiene marcado tipo script
    When el agente revisa el borrador en la cola
    Then el marcado se muestra como texto y no se ejecuta

  Scenario: El borrador truncado a mitad de sintaxis no rompe el render
    Given un borrador cuyo texto se cortó a mitad de una sintaxis Markdown
    When el agente revisa el borrador en la cola
    Then el contenido se muestra sin que el render falle

  Scenario Outline: El borrador con <elemento> Markdown se renderiza como <resultado>
    Given un borrador cuyo texto usa <elemento>
    When el agente revisa el borrador en la cola
    Then se muestra como <resultado>

    Examples:
      | elemento                   | resultado                             |
      | código inline y en bloque  | código con fuente monoespaciada       |
      | una cita (blockquote)      | una cita con sangría                  |
      | una lista ordenada         | una lista numerada                    |
      | una lista no ordenada      | una lista con viñetas                 |
      | una tabla                  | una tabla con bordes                  |
      | un separador horizontal    | una línea separadora fina             |
      | una URL suelta (autolink)  | un enlace                             |
      | una casilla de tarea GFM   | texto plano, sin checkbox interactivo |

  Scenario: El enlace de un borrador se abre en pestaña nueva sin arriesgar la sesión
    Given un borrador con un enlace Markdown
    When el agente hace clic en el enlace
    Then se abre en una pestaña nueva con rel="noopener noreferrer"

  Scenario: Un enlace o imagen con protocolo peligroso queda neutralizado
    Given un borrador con un enlace o imagen usando el protocolo javascript:
    When el agente revisa el borrador en la cola
    Then el enlace o la imagen no ejecuta código, la URL queda neutralizada

  Scenario: El texto alternativo de una imagen se conserva
    Given un borrador con una imagen Markdown con texto alternativo
    When el agente revisa el borrador en la cola
    Then la imagen conserva su atributo alt

  Scenario: Un borrador vacío o solo con espacios no rompe el render
    Given un borrador cuyo texto está vacío o son solo espacios
    When el agente revisa el borrador en la cola
    Then el renderizado no falla

  Scenario: El formato real de las fuentes se renderiza como lista
    Given un borrador con la sección "Fuentes" en el formato que genera el agente
    When el agente revisa el borrador en la cola
    Then la sección de fuentes se muestra como una lista formateada

  Scenario: Editar un borrador usa el editor de Markdown en vez de texto plano
    Given un borrador de la IA en modo edición
    When el agente usa el toolbar del editor para modificar el texto
    Then el campo de edición contiene el string de Markdown resultante

  Scenario: La vista previa al editar un borrador reusa el mismo allow-list que la cola
    Given un borrador de la IA en modo edición, con formato Markdown
    When el agente mira la vista previa del editor
    Then la vista previa se genera con el mismo componente que ya renderiza el borrador en modo
      lectura, no con el motor de renderizado por defecto de la librería del editor

  Scenario: Cambiar de tema mientras se edita un borrador actualiza el editor
    Given un borrador en modo edición con el tema claro activo
    When el agente cambia el tema de la app a oscuro
    Then el editor pasa a modo oscuro

  Scenario: Cambiar de tema mientras se edita un borrador no pierde el texto en curso
    Given un borrador en modo edición con texto sin guardar todavía
    When el agente cambia el tema de la app
    Then el texto en curso sigue presente en el editor, sin recargar la página

  Scenario: Un refresco de la cola en segundo plano no pisa una edición activa
    Given un agente editando un borrador con el editor de Markdown
    When la cola de aprobaciones se refresca en segundo plano (polling)
    Then el texto que el agente está editando no se pierde ni se resetea

  Scenario: Una casilla de lista-de-tareas tecleada a mano se previsualiza como texto plano
    Given un borrador en modo edición con "- [ ] paso" tecleado directamente (no vía toolbar)
    When el agente mira la vista previa del editor
    Then se muestra como texto plano con corchetes, igual que en el hilo ya publicado

  Scenario: Pegar o arrastrar una imagen no la embebe como datos en el propio texto
    Given un borrador en modo edición
    When el agente pega o arrastra un fichero de imagen sobre el editor
    Then el editor NO inserta una imagen embebida en base64/`data:` — solo el botón de imagen del
      toolbar, que inserta una URL externa pegada por el agente
```
