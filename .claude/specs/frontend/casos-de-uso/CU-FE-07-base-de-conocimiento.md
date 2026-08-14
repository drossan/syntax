# CU-FE-07 — Base de conocimiento

> **SDD** (Cockburn + Gherkin). CÓMO para FR-021 de [`../spec.md`](../spec.md). Backend:
> [CU-BE-05](../../backend/casos-de-uso/CU-BE-05-clasificacion-y-retrieval-rag.md),
> [CU-BE-07](../../backend/casos-de-uso/CU-BE-07-ingestion-de-la-kb.md).

- **Ámbito**: frontend (feature KB)
- **Nivel**: objetivo de usuario
- **Actor primario**: usuario/agente con `kb.read`
- **Interesados e intereses**:
  - Usuario — autoservirse buscando en la documentación antes de abrir un ticket.
  - Agente — encontrar el UC relevante para fundamentar una respuesta.

## Precondiciones

- El sujeto tiene `kb.read`; la KB está ingerida.

## Garantía mínima

- Los snippets/citas se muestran como texto inerte (anti-XSS); una búsqueda sin resultados no rompe la vista.

## Garantía de éxito (postcondición)

- El usuario ve resultados relevantes con su dominio/package y puede abrir la vista de un UC.

## Disparador

- El usuario busca o explora por dominio/package.

## Escenario principal (éxito)

1. El usuario busca por texto; la app muestra resultados por relevancia con dominio/package/estado.
2. El usuario explora por dominio/package.
3. Abre la vista de un UC (contenido + relacionados).

## Extensiones (flujos alternativos y de error)

- **1a.** Sin resultados: estado **empty** con sugerencia de reformular.
- **1b.** Error de API: mensaje mapeado + reintento.
- **1c.** Loading: skeleton accesible.

## Reglas de negocio

- **RN-1** — La KB es global (compartida); su lectura no depende del tenant.
- **RN-2** — Los resultados incluyen `estado` (draft/active) como metadato visible.

## Criterios de aceptación (Gherkin)

```gherkin
Feature: Base de conocimiento

  Scenario: Búsqueda semántica con resultados
    Given un usuario con acceso a la base de conocimiento
    When busca un término de producto
    Then obtiene resultados ordenados por relevancia con su dominio y package

  Scenario: Explorar por dominio
    Given la base de conocimiento abierta
    When el usuario explora un dominio concreto
    Then ve los casos de uso de ese dominio

  Scenario: Búsqueda sin resultados
    Given una consulta que no casa con ningún documento
    When el usuario la ejecuta
    Then se muestra un estado vacío que sugiere reformular la búsqueda

  Scenario: Contenido de la KB como texto inerte
    Given un snippet cuyo contenido incluye marcado peligroso
    When se muestra en los resultados
    Then el marcado se presenta como texto y no se ejecuta
```
