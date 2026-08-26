# Session log — `backend-kb-retriever-03` — `embed_query` + settings `RAG_*`

> Append-only. Registro canónico de la tarea (task-lifecycle §Cerrar una tarea).

## 2026-08-25 — Arranque

- **Gate TDD comprobado**: `depends_on: [backend-kb-retriever-01]` en `done`; rama del plan; ninguna
  otra tarea `active` (la `-02` se cerró en `b2ae1c2` antes de mover esta). Tarea → `active/`.
- **Leído en esta sesión**: el task file, `ports/embeddings.py`, `infra/llm/openai_adapter.py`,
  `app/core/config.py`, `tests/test_openai_adapter.py` (patrón de doble: se parchea
  `OpenAIEmbeddings.aembed_*` a nivel de clase, sin red ni clave real) y `tests/test_config.py`
  (autouse que resetea la caché de `get_settings()`).
- **Verificado antes de escribir** (no asumido): `langchain_openai.OpenAIEmbeddings.aembed_query`
  **existe** en el paquete instalado, con firma `(self, text: str, **kwargs: Any) -> list[float]`.

## 2026-08-25 — TDD

- **Rojo primero**: 23 tests nuevos (12 en `test_config.py`, 11 en `test_openai_adapter.py`) escritos
  **antes** de la implementación; rojo confirmado en esta sesión (`23 failed, 66 passed`).
- **Verde**:
  1. `EmbeddingModel.embed_query` en el **puerto**. Se añade ahora porque ahora existe su **consumidor**
     (el retriever de `-05`/`-06`) — el criterio del repo es no fijar firmas sin caller. El docstring de
     módulo dejó de decir que el puerto está "recortado a `embed_documents`", que ya no es cierto.
  2. `OpenAIEmbeddingModel.embed_query` sobre `aembed_query`, reutilizando `_get_client()`
     (instanciación perezosa: la clave se valida al primer uso real, no en import).
  3. Tres settings nuevos en `Settings`: `rag_estado_weight` (0.05, **`ge=0.0`**), `rag_search_window`
     (100 **documentos**, `gt=0`) y `rag_chunks_per_doc` (6, `gt=0`), cada uno con su docstring del
     porqué del valor. **No** se añade `rag_top_k` (eliminado del plan por B3: sería un setting sin
     consumidor).
- **Decisiones de implementación**:
  1. **`embed_query` valida la DIMENSIÓN del vector devuelto**, igual que `embed_documents` valida el
     *número* de vectores. Es el escenario que `scenario-coverage` cazó: una respuesta bien formada con
     datos incompatibles es un modo de fallo **distinto** de "proveedor caído", y sin el control el
     vector llegaría a la comparación pgvector y reventaría como error de driver.
  2. **`PortError` se propaga tal cual** (`except PortError: raise` antes del `except Exception`):
     re-envolverlo escondería el mensaje original dentro de otro genérico. Hay test dedicado.
  3. **`ge=0.0` y no `gt=0.0`** en `rag_estado_weight`: `0.0` es un valor **legítimo** (desempate
     desactivado → orden por similitud pura, y hay escenario del CU para ello). El negativo sí se
     rechaza: invertiría el sentido del boost.

## 2026-08-25 — Gates y cierre

- **`make test`**: **1119 passed** (1091 previos + 23 de TDD + 5 de la deuda cerrada abajo), sin
  regresión.
- **`ruff check` + `ruff format --check` + `mypy app`**: limpios (138 source files). Cero secretos: los
  tests usan `sk-test` y dobles, sin red.
- **Gate de mutation** (`cr-rate --fail-over 20`), **dos pasadas** porque la tarea toca dos ficheros:
  - `app/infra/llm/openai_adapter.py` → **0.00%** a la primera (todos los mutantes muertos).
  - `app/core/config.py` → **35.71%** (25/70): **el gate falló**. Leídos los survivors uno a uno,
    **ninguno estaba en los tres settings nuevos**: 23 caían sobre `max_upload_bytes`
    (`10 * 1024 * 1024`, tarea 08) y 2 eran `@classmethod` de validators (equivalentes).
    - **Causa**: es la **primera vez que se muta `config.py` entero** — hasta ahora `cosmic-ray.toml`
      apuntaba al fichero de cada tarea, así que la deuda nunca había salido a la luz. `max_upload_bytes`
      solo se ejercitaba **inyectado explícitamente** desde `tests/test_router_messages.py`; su
      **default** no lo fijaba ningún test, y es el valor que produce el **413** del contrato.
    - **Resuelto cerrando la deuda ajena** (3 tests: default de 10 MiB + fronteras de `gt=0`), en vez de
      declarar el fallo como preexistente y seguir: era barato y dejaba el gate verde de verdad.
      Segunda pasada: **2.86%** (2/70, los `@classmethod` equivalentes). Gate superado.
- **Gate `/sdd-lint`**: la tarea **no toca artefactos SDD** (los fijó `-01`) — verificado con
  `git diff --name-only HEAD -- .claude/specs/` → vacío. Mecánicos re-ejecutados y limpios.
- **Docs — tres capas**: (1) **docstrings**: `embed_query` en puerto y adaptador (con el porqué de la
  validación de dimensión) y los tres settings; el docstring de módulo de `ports/embeddings.py`
  reescrito porque afirmaba algo que dejaba de ser cierto; (2) **doc técnica**: `.env.example` gana la
  sección "Retrieval de la KB" con los tres `RAG_*` y su semántica; `rag-ingestion.md` §4/§6 ya
  documenta la fórmula y la ventana desde `-01`, así que no se toca; (3) **histórico**: este log.
- **Ficheros**: `app/domain/ports/embeddings.py` (M), `app/infra/llm/openai_adapter.py` (M),
  `app/core/config.py` (M), `.env.example` (M), `tests/test_openai_adapter.py` (M, +11),
  `tests/test_config.py` (M, +15), `cosmic-ray.toml` (M).
- **Tiempo real**: ~2h (estimado 2h).
- **Follow-ups**: ninguno propio. **Aviso a tareas futuras**: mutar `config.py` entero destapa deuda de
  otros planes; si otra tarea vuelve a tocarlo, los 2 survivors `@classmethod` restantes son
  equivalentes (pydantic acepta el validator sin el decorador) y no merecen test.
- **Gate `fact-checker`** (subagente fresco, `model: sonnet`): **16/16 VERIFICADO**, 0 INCORRECTO, 0 NO
  VERIFICABLE. Confirmó por su cuenta que `aembed_query` existe en `langchain_openai 1.5.1` con la firma
  esperada, que `except PortError: raise` va **antes** del `except Exception`, que **no** existe ningún
  `rag_top_k` en `app/`, `tests/` ni `.env.example`, que el único literal de clave es el placeholder
  `sk-test` (4 ocurrencias, ninguna real), y —sobre la deuda ajena— que **antes** de esta tarea ningún
  test construía `Settings` sin inyectar `max_upload_bytes`, así que el default nunca se comprobaba.
  Re-ejecutó `make test` (1119 passed) y `make mutation` sobre `config.py` (2.86%, exit 0).
