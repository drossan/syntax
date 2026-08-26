# Session log — `backend-kb-retriever-02` — `PgVectorStore`: listado y detalle (SQL plano)

> Append-only. Registro canónico de la tarea (task-lifecycle §Cerrar una tarea).

## 2026-08-25 — Arranque

- **Gate TDD comprobado**: `depends_on: [backend-kb-retriever-01]` en **`done`**; rama
  `plan/backend/kb-retriever` (la del plan); `.claude/tasks/active/backend/` vacío antes de mover.
  Tarea → `active/`, `status: active`, `updated: 2026-08-25`.
- **Leído en esta sesión**: el task file, `CU-BE-12` (fuente única del Gherkin), `ports/vectorstore.py`
  (firmas del puerto), `infra/vector/__init__.py` (patrón del adaptador de escritura + `PortError`),
  `_enum_bridge.py`, `entities/business.py::KBDocument`, `models/kb.py` y `tests/test_vector_adapter.py`
  (fixtures `superuser_engine`/`TRUNCATE`, y el `broken_session` para probar `PortError`).
- **Verificado antes de escribir**: `_enum_bridge` expone **`to_orm` y `to_domain`** (la tarea decía
  "verificar su superficie, no asumirla"); `KBDocument.package` es **`String`** en el ORM, no un enum de
  Postgres (`domain`/`estado` sí lo son) → el mapeo de `package` es por valor, no por el puente.

## 2026-08-25 — TDD

- **Rojo primero**: `tests/test_pgvector_store_documents.py` (26 tests) escrito **antes** de la
  implementación; rojo confirmado en esta sesión con
  `ModuleNotFoundError: No module named 'app.infra.vectorstore.pgvector'`.
- **Verde**: `app/infra/vectorstore/pgvector.py` con `PgVectorStore.get_document`/`list_documents`.
  **No** declara `search` — la añade `-06`; una `search` que devolviera `[], 0` mientras tanto sería
  reintroducir el stub por la puerta de atrás (lo prohíbe el `## Fuera de alcance` de la tarea).
  `deps.py`, el router y `StubVectorStore` **sin tocar** (swap atómico en `-07`).
- **Decisiones de implementación**:
  1. **`_filtered()` como único sitio de las tres condiciones**, compartido por el `COUNT` del `total` y
     por el `SELECT` de los `items`. Si divergieran, el front paginaría sobre un total que no le
     corresponde. Es también lo que hace que `total` cuente el conjunto **filtrado y sin paginar**.
  2. **`ORDER BY uc_id ASC` explícito** (RN-6): el test lo fija insertando en orden inverso, porque sin
     `ORDER BY` Postgres puede devolver las filas en orden de inserción y el test pasaría por accidente.
  3. **Enums por valor en las dos direcciones**: `to_orm` al filtrar (el enum ORM es el que entiende
     Postgres) y `to_domain` al mapear la fila; `package` se reconstruye con `Package(row.package)`.
  4. **Tests que insertan con el ORM directamente**, no con `SqlAlchemyKBIndexWriter`: este módulo
     verifica el adaptador de LECTURA, y pasar por el de escritura ataría sus tests a un adaptador que
     no está bajo prueba.
- **Hallazgo real durante el ciclo rojo→verde** (no estaba en el plan ni en la tarea): un `uc_id` con un
  byte **NUL** (`%00` en la URL) **revienta en el driver** y salía como `PortError` → **502**, cuando el
  escenario *Un identificador con forma inesperada no rompe la consulta* pide **no encontrado**. Salida
  real observada: `PortError: fallo al leer el documento de KB 'UC-1\x00'`. **Resuelto** descartando el
  `\x00` **antes** de consultar: Postgres no puede almacenar `\x00` en una columna de texto, así que ese
  documento no existe **por construcción** — no es un parche, es la respuesta correcta. Un 502 ahí
  culparía a la base de datos de una entrada del cliente.
  - El mismo test parametrizado cubre los **comodines de `LIKE`** (`UC-%`, `UC_1`): si la implementación
    usara `LIKE` en vez de `=`, casarían con `UC-1` y devolverían un documento en vez de `None`.

## 2026-08-25 — Gates y cierre

- **`pytest` del módulo**: **27 passed**. **`make test`** completo: **1091 passed** (1064 previos + 27
  nuevos), **sin regresión**.
  - ⚠️ **Afirmación corregida tras el gate `fact-checker`**: esta línea decía **1090**. Era la cifra de
    la pasada que corrí **antes** de reforzar los tests con el gate de mutation (26 tests nuevos); al
    añadir el 27º (`…defaults_to_the_contract_page_size`) la suite pasó a **1091**, y no re-ejecuté
    `make test` antes de escribirlo. El verificador lo ejecutó y obtuvo `1091 passed in 98.61s`.
- **`ruff check` + `ruff format --check` + `mypy app`**: limpios (138 source files). `mypy --strict`
  obligó a acotar el genérico de `_filtered` a `Select[T: tuple[object, ...]]` — `Select` exige que su
  argumento de tipo sea subtipo de `tuple[Any, ...]`.
- **Gate de mutation** (`make mutation`, `cosmic-ray`, `cr-rate --fail-over 20` = `break: 80`) sobre
  `app/infra/vectorstore/pgvector.py`: primera pasada **2.58%** (4/155). Survivors leídos uno a uno:
  1. **REAL** — `domain == …` → `domain >= …`: el test de filtro por dominio tenía un único vecino, y
     ordenaba **antes** en el enum de Postgres, así que la desigualdad daba el mismo resultado. Test
     reforzado con un dominio que ordena **después** (`seo_sitemaps_and_edge`).
  2. **REAL** — `page_size: int = 20` → `21`/`19` (dos mutantes): ningún test ejercitaba el **default**.
     Test nuevo con 23 documentos que fija el default en **20**, que es valor del contrato compartido.
  3. **EQUIVALENTE, aceptado** — `*` → `/` en la firma (keyword-only → positional-or-keyword): todas las
     llamadas son por keyword, y matarlo exigiría un test que compruebe la sintaxis de Python, no un
     comportamiento.
  - Segunda pasada: **0.65%** (1/155, el equivalente). Gate superado con margen.
- **Gate `/sdd-lint`**: esta tarea **no toca ningún artefacto SDD** (los fijó `-01`) — verificado con
  `git diff --name-only HEAD -- .claude/specs/` → **vacío**. Los checks mecánicos se re-ejecutaron igual
  (estados MADR, `[NECESITA ACLARACIÓN`, formato de ids) y salen limpios. El pase **semántico** valida
  exactamente los mismos bytes que ya validó en `-01` hace unos minutos (0 ERROR), así que no se relanza:
  se declara aquí en vez de omitirlo en silencio.
- **Docs — tres capas**: (1) **docstrings** de todo símbolo público de `pgvector.py`, incluido el porqué
  del reparto escritura/lectura del SQL de `kb_document` y el del descarte del `\x00`; (2) **doc
  técnica**: sin cambios — el "qué" y el "porqué" ya están en `CU-BE-12` y `ADR-0018` (`-01`), y este
  adaptador todavía no es observable desde la API (el swap es `-07`); (3) **histórico**: este log.
- **Ficheros**: `app/infra/vectorstore/pgvector.py` (nuevo), `tests/test_pgvector_store_documents.py`
  (nuevo), `cosmic-ray.toml` (M, apunta a los ficheros de esta tarea).
- **Tiempo real**: ~2h (estimado 3h).
- **Follow-ups**: ninguno propio. Pendientes heredados de `-01` que tocan a tareas siguientes: `-06`
  añade `search` sobre esta misma clase; `-07` cablea `deps.py`, borra el stub y corrige el docstring de
  `ports/vectorstore.py:5` (que todavía promete que el retriever real llegará "sin tocar el router").
- **Gate `fact-checker`** (subagente fresco, `model: sonnet`): **14/15 VERIFICADO, 1 INCORRECTO, 0 NO
  VERIFICABLE**. El INCORRECTO es el conteo de la suite (1090 → **1091**), corregido arriba: bloqueaba
  el cierre hasta arreglar la **afirmación**, no el código (la suite estaba verde en ambas pasadas).
  Verificó por su cuenta que las firmas de `PgVectorStore` **coinciden campo a campo** con el `Protocol`,
  que no existe ningún `search`, que `COUNT` e `items` pasan por la **misma** `_filtered()` y que el
  `COUNT` no lleva `offset`/`limit`, que ambos métodos envuelven en `PortError`, que el `ORDER BY` es
  explícito, que `git diff` no toca `deps.py`/router/stub/frontend/specs, y re-ejecutó `make mutation`
  en exclusiva obteniendo **0.65** con exit code 0.
