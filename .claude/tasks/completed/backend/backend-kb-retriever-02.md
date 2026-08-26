---
id: backend-kb-retriever-02
package: backend
plan: kb-retriever
status: done
priority: 1
depends_on: [backend-kb-retriever-01]
estimate: 3h
actual: 2h
created: 2026-08-24
updated: 2026-08-25
---

# `PgVectorStore`: listado y detalle de documentos (SQL plano)

## Description

`list_documents` y `get_document` **no necesitan vectores**: son SQL sobre `kb_document`. Hoy los sirve
`StubVectorStore` devolviendo `[], 0` y `None`, y por eso `/kb` y `/kb/[uc_id]` están vacíos en el panel.

Esta tarea va **temprana a propósito** (hallazgo D1' de `design-review`): es la mitad del adaptador que
no depende de embeddings, ventana, rerank ni dedup, así que se puede implementar y verificar sin nada de
eso. **No recablea `deps.py`** — el swap es atómico en `-07`, porque el router resuelve los tres
endpoints por la misma dependencia `get_vector_store()`.

Specs: `.claude/specs/backend/casos-de-uso/CU-BE-12-...md` (RN-6, RN-7),
`.claude/specs/general/api-contract.md` (paginación estable), `.claude/specs/backend/data-model.md` §4.3.

## Spec

- **Nuevo** `app/infra/vectorstore/pgvector.py` con la clase `PgVectorStore`, adaptador de
  `app.domain.ports.vectorstore.VectorStore`. Constructor: `__init__(self, session: AsyncSession, ...)`
  (las dependencias de `search` las añade `-06`; no adelantarlas aquí).
- `get_document(uc_id) -> KBDocument | None`: `SELECT` sobre `KBDocumentModel` por `uc_id` (tiene
  `UniqueConstraint`), mapeado a la entidad `app.domain.entities.business.KBDocument`. `None` si no existe
  — el 404 lo lanza el router, que ya lo hace (`routers/kb.py:104-106`).
- `list_documents(*, domain, package, estado, page, page_size) -> tuple[list[KBDocument], int]`:
  - Filtros opcionales combinables (`AND`), cada uno omitido si es `None`.
  - **`ORDER BY uc_id ASC`** — determinista y estable, porque `uc_id` es único (hallazgo A5). Sin esto,
    Postgres devuelve orden arbitrario y `useKbRelated` del front pinta documentos arbitrarios como
    "relacionados".
  - `total` = `COUNT(*)` **con los mismos filtros** y **sin** paginación.
  - Offset = `(page - 1) * page_size`.
- Conversión de enums ORM↔dominio con el puente existente: `app/infra/db/repositories/_enum_bridge.py`
  (`to_orm`, y su inverso si existe — **verificar el módulo antes de usarlo**, no asumir su superficie).
- Errores de infraestructura → `app.domain.errors.PortError`, igual que hace
  `SqlAlchemyKBIndexWriter` (`app/infra/vector/__init__.py:44-45`). `PortError` ya mapea a 502. **Este
  camino no toca embeddings**: un fallo aquí es de base de datos, y debe distinguirse de un listado
  vacío (hallazgo de `scenario-coverage`).
- **Glosarios** (RN-9 del CU): son filas normales de `kb_document` con `uc_id` de la forma
  `__glosario__:<dominio>` (`GLOSARIO_UC_ID_PREFIX` en `app/ingestion/parser.py:46`) — **verificado**.
  Se listan y se abren como cualquier otro documento; **no** se filtran. El adaptador no necesita
  lógica especial: el escenario existe para fijar que ese `uc_id` sintético es un identificador
  válido de la API y no rompe el mapeo ORM→entidad.
  - ⚠️ **Sesgo heredado, a NO arreglar aquí**: la ingestión les asigna `Package.syntax_core` y
    `KbEstado.active` por defecto (`app/ingestion/pipeline.py:47-48`) porque su formato no los trae,
    así que aparecen al filtrar por esos valores sin pertenecer realmente a ellos. Es un defecto de la
    **ingestión**; `-01` lo documenta en el CU y el ADR. Corregirlo exigiría migración + re-ingesta.
- **`updated` puede ser `None`** (`KBDocument.updated: datetime | None`): no es un error, se sirve como
  ausente.
- **Tests de INTEGRACIÓN** contra Postgres de docker-compose, siguiendo el patrón de
  `tests/test_vector_adapter.py`: fixture `superuser_engine` + `TRUNCATE embedding, kb_chunk,
  kb_document RESTART IDENTITY CASCADE`. KB es global → sin RLS que verificar.
- **Docstrings** en todo símbolo público, al escribirlo.

## Fuera de alcance

- `PgVectorStore.search` — la implementa `-06`. Aquí puede no existir todavía, o existir declarada;
  lo que **no** puede es devolver `[], 0` en silencio (sería reintroducir el stub).
- Recablear `get_vector_store()` en `app/core/deps.py` → `-07`.
- Borrar `StubVectorStore` → `-07`.
- Tocar `app/api/v1/routers/kb.py` → `-06`/`-07`.
- Tocar **código** del frontend.

## Scenarios (Gherkin)

Criterios de aceptación en el caso de uso (fuente única):

- [`.claude/specs/backend/casos-de-uso/CU-BE-12-consulta-de-la-kb-desde-el-panel.md`](../../../specs/backend/casos-de-uso/CU-BE-12-consulta-de-la-kb-desde-el-panel.md)

Escenarios que materializa esta tarea:

- *Abrir un documento existente*
- *Un documento sin fecha de actualización se sirve igualmente*
- *Abrir un documento inexistente*
- *Un identificador con forma inesperada no rompe la consulta*
- *Los glosarios son documentos de pleno derecho* (RN-9)
- *Un glosario se abre por su identificador* (RN-9; escenario separado del anterior al corregir un AVISO
  de `/sdd-lint` en `-01`: el `When` de listar no dispara la apertura del detalle)
- *El listado de documentos es estable entre páginas* (RN-6)
- *Pedir una página más allá del listado*
- *Un fallo de la base de datos no se disfraza de KB vacía*
- *Los filtros acotan la búsqueda* — la mitad de `list_documents` (la de `/kb/search` es de `-06`)

## Provides

- `app/infra/vectorstore/pgvector.py::PgVectorStore` con `list_documents` y `get_document` reales y
  verificados contra Postgres. `-06` añade `search` sobre esta misma clase; `-07` la cablea en `deps.py`.

## Definition of Done

- [x] Tests escritos ANTES de la implementación (TDD) — Red → Green → Refactor
- [x] Cada escenario del CU que materializa esta tarea tiene al menos un test (camino feliz + bordes)
- [x] Todos los tests en verde (`make test`, sin regresión sobre los 1064)
- [x] Spec cumplida; lo declarado en `Provides` queda realmente disponible para las tareas dependientes
- [x] Lint / format / typecheck OK (`ruff`, `mypy --strict`)
- [x] Gate de mutation testing superado (`make mutation`, cosmic-ray `break: 80`) sobre los ficheros tocados
- [x] **Gate `sdd-lint` superado** — tras `mutation`, antes de `fact-checker`
- [x] Gate de `fact-checker` superado — antes de commit/resumen
- [x] **SDD** — sin cambios de spec/CU (los fijó `-01`); declararlo así en el session log
- [x] Documentación actualizada — tres capas:
  - [x] **Docstrings** — todo símbolo público de `pgvector.py`
  - [x] **Doc técnica** — donde aplique
  - [x] **Histórico** — session log en `.claude/context/backend/backend-kb-retriever-02.md`

> ⚠️ **No solapar `pytest` con `cosmic-ray exec`**: cosmic-ray muta el fichero fuente **en disco** y un
> `pytest` concurrente falla en falso.
