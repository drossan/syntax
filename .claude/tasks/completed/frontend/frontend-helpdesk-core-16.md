---
id: frontend-helpdesk-core-16
package: frontend
plan: helpdesk-core
status: done
priority: 3
depends_on: [frontend-helpdesk-core-06, backend-skeleton-foundation-06]
estimate: 3h
actual: 1.3h
issue:
created: 2026-08-11
updated: 2026-08-13
---

# Base de conocimiento (buscar / explorar)

## Description

UI de la KB: buscador semántico + explorar por dominio (17) / package, y vista de un documento UC con sus
**relacionados**. Consume `GET /kb/search` y `/kb/documents/{uc_id}`.

## Spec

- Buscador semántico (query + filtros dominio/package/estado); resultados con título, dominio, snippet y `estado`.
- Explorar por dominio/package (navegación por facetas).
- Vista de documento UC (secciones) + **relacionados** (grafo `Relacionado:`).
- Estados empty (sin resultados) / loading / error.

## Fuera de alcance

- Edición de la KB. Ingestión (backend). BM25 (diferido).

## Scenarios (Gherkin)

```gherkin
Feature: Base de conocimiento

  Scenario: Búsqueda con resultados
    Given una KB con documentos de varios dominios
    When se busca un término presente
    Then se muestran los resultados relevantes con su dominio y estado

  Scenario: Búsqueda sin resultados
    Given una consulta que no coincide con ningún documento
    When se ejecuta la búsqueda
    Then se muestra el estado vacío con sugerencia de reformular

  Scenario: Documento con relacionados
    Given un documento UC con documentos relacionados
    When se abre el documento
    Then se muestran sus secciones y los enlaces a relacionados
```

## Provides

- Páginas de búsqueda/explorar/documento de la KB.

## Definition of Done

- [x] Tests ANTES (TDD): con resultados, sin resultados (reformular), filtros, relacionados (mismo dominio, self excluido), documento 404.
- [x] Buscador + facetas (dominio/estado) + vista de documento + relacionados (heurística por dominio; ver session log).
- [x] Lint + typecheck OK; gate de mutation 90.74% (break 80); estados loading/error/empty + a11y (searchbox, nav relacionados).
- [x] `Provides` disponible; `fact-checker` 10/10 VERIFICADO; docs 3 capas + session log. *(secciones/grafo relacionados: pendientes de schema KB — gap)*
