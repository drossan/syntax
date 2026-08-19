# Session log — backend-routers-core-09

Tarea: puerto `VectorStore` (nuevo, recortado a lo que el router `kb` necesita hoy) + adaptador STUB
(`StubVectorStore`) + router `kb` completo (búsqueda, listado, detalle de documentos). Depends_on: 05
(`done`). Última tarea del plan `routers-core` (9/9).

## Entradas

- 2026-08-19 — Arranque. Movida de `pending/` a `active/`, `status: pending`→`status: active`.

## Resumen

`app/domain/entities/enums.py` gana `KbEstado` (ya existía en el ORM, faltaba en dominio) y `Package`
(nuevo en ambos lados — el contrato lo declara como enum de 5 valores fijos, aunque la columna real
`kb_document.package` sea `sa.String()` sin `pg_enum`; se trata como catálogo fijo del contrato, no
como reflejo 1:1 de un tipo de columna). `app/domain/entities/business.py` gana `KBDocument`/
`KBSearchHit`. `app/domain/ports/vectorstore.py`: `VectorStore` (antes solo un docstring "GUIÓN") con
`search`/`get_document`/`list_documents`, devolviendo `(items, total)` en vez de `PageResult` (este
puerto no comparte el árbol de repos de negocio/identidad). `app/infra/vectorstore/stub.py` (nuevo):
`StubVectorStore` — sin ninguna rama condicional, siempre vacío/`None`. Router `kb.py`: los 3 endpoints
del contrato (ya existían en `api-contract.yaml`, sin cambios de spec necesarios).

## Decisiones técnicas + porqué

- **`Package` es un enum de dominio nuevo sin equivalente `pg_enum` en la columna real**: el contrato
  fija 5 valores (`syntax-api/cx/core/ax/render`) pero `kb_document.package` es `sa.String()` plano —
  se trata la validación como responsabilidad del CONTRATO (capa API), no como un reflejo de un tipo de
  columna que no existe. `KbEstado`, en cambio, SÍ tiene equivalente ORM (`pg_enum`), añadido también al
  test de drift domain↔ORM (`test_enum_drift_by_value`, con el par nuevo `("KbEstado", "KbEstado")`) —
  `Package` queda fuera de ese test a propósito (no hay ORM enum con el que compararlo).
- **`require_capability("kb.read")` se reusa tal cual, sin caso especial** para KB pese a ser un
  recurso global: `kb_document`/`kb_chunk` no llevan `TenantMixin`, así que el GUC que
  `global_scope`/`tenant_scope` fije es irrelevante (ninguna política RLS lo lee) — usar el mismo
  mecanismo que el resto de routers es más simple que inventar una dependencia nueva solo para KB.
- **`VectorStore.search`/`list_documents` devuelven `tuple[list[T], int]`, no `PageResult[T]`**: este
  puerto vive fuera del árbol de `app.domain.ports.repositories` (no comparte su `PageResult`
  genérico) — mantenerlo autocontenido evita un acoplamiento innecesario entre el futuro retriever
  (tarea 14) y los puertos de negocio/identidad.
- **Mutation gate del stub declarado N/A** (permitido explícitamente por la propia DoD de la tarea):
  `StubVectorStore` no tiene ninguna rama condicional (`grep -c "if \|elif \|else:"` → 0) — no hay
  mutantes de comportamiento real que perseguir, solo métodos que devuelven una constante fija.
- **Gate `/sdd-lint` declarado N/A** (también explícito en la DoD/Scenarios de la tarea): los 3 paths
  del router (`/kb/search`, `/kb/documents`, `/kb/documents/{uc_id}`) YA EXISTÍAN en `api-contract.yaml`
  desde antes de esta tarea — no hubo ningún cambio de spec/CU que auditar.

## Tests corridos + resultado

- `tests/test_vectorstore_stub.py` (nuevo, **4 tests**): `search`/`list_documents` siempre vacíos
  (con y sin filtros), `get_document` siempre `None` — deterministas.
- `tests/test_router_kb.py` (nuevo, **10 tests**): los 6 escenarios Gherkin de la tarea (403 sin
  `kb.read` en los 3 endpoints, página vacía determinista en `search`/`documents`, 404 en el detalle,
  `q` obligatorio, KB no depende del tenant del subject — dos subjects de tenants distintos obtienen
  la MISMA respuesta) + refuerzos de mutación (`page_size` en sus límites exactos, filtro `domain`
  inválido → 422).
- `tests/test_domain_entities.py`: añadido el par `("KbEstado", "KbEstado")` al test de drift
  domain↔ORM (existía el enum ORM desde antes, faltaba el de dominio).
- Suite completa del backend (`pytest -q`): **602 tests, verde**, sin regresiones.
- `ruff check .`/`ruff format --check .`: OK. `mypy app` (strict): `Success: no issues found in 118
  source files`.
- Mutation (`cosmic-ray`, `--fail-over 20`): `app/api/v1/routers/kb.py`, **14.29%** survival → PASA
  directamente (sin rondas de refuerzo). `app/infra/vectorstore/stub.py`: N/A documentado (ver arriba).
- `/sdd-lint`: N/A (ver arriba) — no se lanzó ningún subagente semántico para esta tarea.
- `fact-checker`: pendiente de lanzar tras este session log.

## Docs actualizadas

- Docstrings de `app/domain/ports/vectorstore.py` (por qué `(items, total)` y no `PageResult`, por qué
  KB no lleva `tenant_id` en ninguna firma), `app/infra/vectorstore/stub.py` (por qué el stub no es un
  placeholder silencioso — el shape ya es el final), `app/api/v1/routers/kb.py` (por qué
  `require_capability` se reusa sin caso especial pese a ser global), `app/domain/entities/enums.py`
  (`Package` sin equivalente ORM, a propósito). Este session log.

## Ficheros / commits

- `backend/app/domain/ports/vectorstore.py` (contenido real), `backend/app/infra/vectorstore/__init__.py`
  (nuevo), `backend/app/infra/vectorstore/stub.py` (nuevo), `backend/app/api/v1/routers/kb.py` (de
  esqueleto a código real), `backend/app/api/v1/schemas/kb.py` (nuevo).
- `backend/app/domain/entities/enums.py` (`KbEstado`/`Package`), `backend/app/domain/entities/
  business.py` (`KBDocument`/`KBSearchHit`), `backend/app/core/deps.py` (`get_vector_store`),
  `backend/app/main.py` (monta el router `kb`).
- `backend/tests/test_vectorstore_stub.py` (nuevo), `backend/tests/test_router_kb.py` (nuevo),
  `backend/tests/test_domain_entities.py` (par `KbEstado` en el test de drift).
- `backend/cosmic-ray.toml` (apunta a `app/api/v1/routers/kb.py`, último módulo mutado).
- Commit: uno solo, `backend-routers-core-09: feat(backend): puerto VectorStore + stub + router kb`.

## Tiempo real

- `estimate: 2h` → real: cercana a la estimación — la tarea más pequeña del plan (sin RLS, sin
  autorización en runtime, sin dependencias nuevas), solo ampliada por diseñar `Package`/`KBDocument`/
  `KBSearchHit` desde cero (no existían en absoluto, ni en dominio ni en ORM para `Package`).

## Follow-ups

- Ninguno propio. `StubVectorStore` queda listo para que la tarea 14 (retriever real) lo sustituya sin
  tocar el router `kb` ni el puerto — el shape de `KBDocument`/`KBSearchHit` ya es el final.
- **Cierra el plan `backend-routers-core` (9/9 tareas)**: con esta tarea, las 9 tareas del plan quedan
  `done`. Pendiente: retro del plan + actualizar su frontmatter a `status: completed` (fuera del
  alcance de esta tarea individual, es el cierre del PLAN completo).
