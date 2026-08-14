# CU-FE-04 — Alta de ticket

> **SDD** (Cockburn + Gherkin). CÓMO para FR-013 de [`../spec.md`](../spec.md). Validación RHF+Zod.
> Backend: [CU-BE-04](../../backend/casos-de-uso/CU-BE-04-ciclo-de-vida-del-ticket.md).

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
```
