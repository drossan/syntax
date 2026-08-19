---
id: backend-routers-core-09
package: backend
plan: routers-core
status: pending
priority: 3
depends_on: [backend-routers-core-05]
estimate: 2h
actual:
issue:
created: 2026-08-19
updated: 2026-08-19
---

# Puerto VectorStore (nuevo, recortado) + adaptador stub + router kb

## Description

`kb` entra en este plan con un adaptador **stub** (decisión de `grilling`): el retriever real (embeddings
+ pgvector ANN) es la tarea 14, todavía inexistente. Este router queda funcional y ⊇ contrato, pero con
resultados vacíos/deterministas — **documentado como comportamiento esperado**, no un bug, hasta que la
14 sustituya el adaptador. Spec: CU-BE-05 (parcial — solo la superficie HTTP, no el retrieval real).

## Spec

- **`app/domain/ports/vectorstore.py`** (nuevo, recortado a lo que `kb` necesita hoy): `VectorStore`
  (Protocol, async): `search(query: str, filters: dict, page, page_size) -> tuple[list[KBSearchHit],
  int]`, `get_document(uc_id: str) -> KBDocument | None`, `list_documents(filters, page, page_size) ->
  tuple[list[KBDocument], int]`.
- **`app/infra/vectorstore/stub.py`** (nuevo): `StubVectorStore` — `search`/`list_documents` devuelven
  siempre `([], 0)`; `get_document` siempre `None`. Docstring explícito: "sin implementación real hasta
  la tarea 14; no es un placeholder silencioso — el shape de la respuesta es el final".
- **Router `kb.py`**:
  - `GET /kb/search` (`kb.read`) → `Page[KBSearchHit]` (vacío hoy).
  - `GET /kb/documents` (`kb.read`) → `Page[KBDocument]` (vacío hoy).
  - `GET /kb/documents/{uc_id}` (`kb.read`) → 404 siempre hoy (documentado, no un bug: no hay documentos
    reales todavía).
  - Sin RLS de tenant (KB es global) — `require_capability("kb.read")` sin abrir `tenant_scope`.

## Fuera de alcance

- El retriever real (embeddings, pgvector ANN, reranking, citas) → tarea 14.
- Ingesta de la KB → tarea 13.

## Scenarios (Gherkin)

<!-- SDD: CU-BE-05 cubre el retrieval real (tarea 14); esta tarea solo monta la superficie HTTP con un
     stub determinista → Gherkin LOCAL, "sin cambios de spec/CU" (no añade comportamiento de negocio de
     CU-BE-05, solo expone el contrato con una implementación provisional documentada). -->

```gherkin
Feature: router kb con adaptador stub

  Scenario: buscar en kb sin capacidad kb.read se rechaza
    Given un subject sin la capacidad kb.read
    When hace GET /kb/search?q=algo
    Then recibe 403

  Scenario: buscar en kb con la capacidad devuelve una página vacía determinista
    Given un subject con kb.read
    When hace GET /kb/search?q=algo
    Then recibe 200 con Page{items: [], total: 0} (shape del contrato, sin resultados aún)

  Scenario: buscar en kb sin el parámetro q obligatorio se rechaza
    Given un subject con kb.read
    When hace GET /kb/search sin el parámetro q
    Then recibe 422 (q es required en el contrato)

  Scenario: listar documentos devuelve una página vacía determinista
    Given un subject con kb.read
    When hace GET /kb/documents
    Then recibe 200 con Page{items: [], total: 0}

  Scenario: pedir un documento concreto da 404 (no hay documentos reales todavía)
    Given un subject con kb.read
    When hace GET /kb/documents/UC-API-001
    Then recibe 404 problem+json

  Scenario: kb no filtra por tenant (recurso global)
    Given subjects de dos tenants distintos, ambos con kb.read
    When ambos hacen GET /kb/search?q=algo
    Then ninguno necesita tenant_scope — la respuesta no depende de su tenant_id
```

## Provides

`app.domain.ports.vectorstore.VectorStore` (nuevo) + `StubVectorStore` en `app.infra.vectorstore.stub`;
router `kb` completo, listo para que la tarea 14 sustituya el adaptador sin tocar el router.

## Definition of Done

- [ ] Tests escritos ANTES de la implementación (Red → Green → Refactor).
- [ ] Cada escenario tiene al menos un test de integración.
- [ ] Todos los tests en verde (`make test`).
- [ ] `Provides` disponible; el router no importa nada de `app.infra.vectorstore` más allá del puerto.
- [ ] `ruff check` (+`S`) + `ruff format --check` + `mypy` strict OK.
- [ ] Gate de mutation: puede ser N/A documentado si el stub no tiene ramas condicionales reales (a
  confirmar durante la tarea; si el router sí tiene lógica de paginación/filtros, el gate aplica a esa
  parte).
- [ ] Gate `/sdd-lint`: N/A (sin cambios de spec/CU, declarado en Scenarios).
- [ ] Gate de `fact-checker`.
- [ ] Documentación: docstring explícito de por qué el stub devuelve vacío (no es un bug); session log.
