# CU-FE-04 — Alta de ticket

> **SDD** (Cockburn + Gherkin). CÓMO para FR-013 de [`../spec.md`](../spec.md). Validación RHF+Zod.
> Backend: [CU-BE-04](../../backend/casos-de-uso/CU-BE-04-ciclo-de-vida-del-ticket.md). Decisión del
> editor de la descripción: [ADR-0021](../../adr/0021-editor-markdown-nativo-con-preview-reusando-el-allow-list.md).

- **Ámbito**: frontend (feature tickets — alta)
- **Nivel**: objetivo de usuario
- **Actor primario**: usuario/agente con `ticket.create`
- **Interesados e intereses**:
  - Usuario — abrir un ticket con datos válidos sin fricción.
  - Plataforma — no enviar formularios inválidos a la API.

## Precondiciones

- El sujeto tiene `ticket.create`.

## Garantía mínima

- Un formulario inválido no se envía; los errores se muestran junto a su campo.

## Garantía de éxito (postcondición)

- El ticket se crea y el usuario llega a su detalle/bandeja actualizada.

## Disparador

- El usuario abre el formulario de alta y lo envía.

## Escenario principal (éxito)

1. El usuario rellena asunto/descripción/prioridad.
2. La validación (RHF+Zod) pasa; se envía la creación.
3. La app confirma e invalida la bandeja (aparece el ticket nuevo).

## Extensiones (flujos alternativos y de error)

- **2a.** Campos inválidos: se muestran errores por campo y no se envía.
- **3a.** Error de API (`problem+json` con `errors[]`): se mapea a errores de campo + toast.
- **1a.** (ADR-0021) El campo de descripción se compone con `MarkdownEditor` (toolbar + preview), no
  un `<textarea>` plano — el valor sigue siendo el mismo string de Markdown que consume la validación
  Zod existente, sin cambio de contrato.

## Reglas de negocio

- **RN-1** — Validación en cliente **y** confianza en la validación del servidor (el cliente no es autoridad).
- **RN-2** — Tras el alta se invalida la caché de la bandeja.

## Criterios de aceptación (Gherkin)

```gherkin
Feature: Alta de ticket

  Scenario: Alta con datos válidos
    Given un usuario con permiso para crear tickets
    When envía el formulario de alta con datos válidos
    Then el ticket se crea y aparece en su bandeja

  Scenario: Validación de formulario inválido
    Given el formulario de alta con un campo obligatorio vacío
    When el usuario intenta enviarlo
    Then el envío se bloquea y se muestra el error junto al campo

  Scenario: Errores de campo devueltos por la API
    Given un envío que la API rechaza con errores por campo
    When se recibe la respuesta de error
    Then los errores se muestran en sus campos correspondientes

  Scenario: La descripción se compone con el editor de Markdown
    Given el formulario de alta de ticket
    When el usuario usa el toolbar del editor para dar formato a la descripción
    Then el campo contiene el string de Markdown resultante, válido para la misma validación de
      siempre

  Scenario: La vista previa de la descripción usa el mismo renderer que el hilo publicado
    Given una descripción con formato Markdown en curso de edición
    When el usuario mira la vista previa del editor
    Then la vista previa se genera con el mismo componente y allow-list que renderiza el mensaje una
      vez publicado, no con un renderer distinto

  Scenario: El Markdown compuesto en el editor llega intacto a la creación del ticket
    Given una descripción compuesta con el editor de Markdown
    When el usuario envía el formulario de alta
    Then el ticket se crea con el mismo string de Markdown que el editor mostraba

  Scenario: Una descripción vacía sigue permitiendo crear el ticket
    Given el formulario de alta con el editor de descripción vacío
    When el usuario envía el formulario
    Then el ticket se crea sin descripción, igual que con el textarea anterior

  Scenario: Usar el toolbar marca el formulario como modificado
    Given el formulario de alta recién abierto
    When el usuario usa un botón del toolbar del editor (no teclea directamente)
    Then el formulario queda marcado como modificado

  Scenario: Un formulario modificado por el toolbar activa el aviso de salida sin guardar
    Given el formulario de alta marcado como modificado tras usar el toolbar del editor
    When el usuario intenta abandonar la página
    Then el aviso de salida sin guardar se activa

  Scenario: El editor no está disponible antes de la hidratación del cliente
    Given la página de alta de ticket recién servida
    When el editor de Markdown aún no se ha hidratado en el navegador
    Then el usuario ve un estado de carga reconocible, no un campo vacío indistinguible de "sin valor"
```
