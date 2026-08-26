---
id: backend-kb-retriever-03
package: backend
plan: kb-retriever
status: done
priority: 1
depends_on: [backend-kb-retriever-01]
estimate: 2h
actual: 2h
created: 2026-08-24
updated: 2026-08-25
---

# `embed_query` en el puerto de embeddings + settings `RAG_*`

## Description

`app/domain/ports/embeddings.py` está recortado a `embed_documents` **a propósito**: su docstring dice
*"sin `embed_query` todavía — lo fijará el retriever (14), sin caller en este plan: no se fija una firma
sin consumidor"*. Este plan **es** ese consumidor, así que toca fijarla.

También faltan los settings que gobiernan el retrieval: `RAG_ESTADO_WEIGHT` solo existe hoy como
mención en el docstring-guión de `app/rag/reranker.py` y en ADR-0010 — **el campo no existe** en
`app/core/config.py`.

Specs: `.claude/specs/backend/rag-ingestion.md` §5 (embeddings) y §4 (peso de `estado`), `ADR-0018`.

## Spec

- **`app/domain/ports/embeddings.py`**: añadir al `Protocol` `EmbeddingModel`:
  ```python
  async def embed_query(self, text: str) -> list[float]:
  ```
  con su docstring (`:raises app.domain.errors.PortError:` igual que `embed_documents`). Actualizar el
  docstring de módulo: ya no es cierto que el puerto esté "recortado a `embed_documents`".
- **`app/infra/llm/openai_adapter.py`**: implementar `OpenAIEmbeddingModel.embed_query` sobre
  `client.aembed_query(text)` — **verificado** que existe en el `langchain_openai` instalado. Mismo
  tratamiento de errores que `embed_documents`: `PortError` propagado tal cual, cualquier otra excepción
  envuelta en `PortError`. Reutiliza `_get_client()` (instanciación perezosa, valida
  `openai_api_key` al primer uso real).
  - **Validar la longitud del vector devuelto** contra `settings.embedding_dim`, en el mismo espíritu
    que `embed_documents` valida el número de vectores: un vector de dimensión incorrecta reventaría más
    tarde, en la comparación pgvector, con un error de driver en vez de uno de puerto.
- **`app/core/config.py`** — campos nuevos en `Settings`, cada uno con su docstring explicando el valor
  y de dónde sale:
  - `rag_estado_weight: float = Field(default=0.05, ge=0.0)` — boost multiplicativo de `active`
    (`score * (1 + w)`); `draft` no se toca. `0.0` = desempate desactivado, valor legítimo.
  - `rag_search_window: int = Field(default=100, gt=0)` — ventana de recuperación **en DOCUMENTOS**;
    100 = el `page_size` máximo del contrato, para que la página 1 nunca salga truncada.
  - `rag_chunks_per_doc: int = Field(default=6, gt=0)` — factor de over-fetch de chunks sobre la
    ventana (~5.7 chunks/doc medidos en el corpus real, redondeado hacia arriba).
- **Tests unit** con doble del cliente (patrón de `tests/test_openai_adapter.py`) + tests de `Settings`
  (patrón de `tests/test_config.py`, que tiene su propio autouse para resetear el cache de
  `get_settings()`). **Sin red y sin clave de OpenAI.**
- **Docstrings** en todo símbolo público, al escribirlo.

## Fuera de alcance

- `rag_top_k`: **eliminado del plan** (hallazgo B3) — sería un setting sin consumidor hasta el plan del
  agent-graph, contradiciendo el criterio que este mismo plan invoca.
- Caché de vectores de consulta: descartada en `grilling` (D1), documentada como follow-up en `ADR-0018`.
- Usar `embed_query` desde algún adaptador: eso es `-05`/`-06`.
- `OpenAIChatModel` (sigue en GUIÓN; es del plan del agent-graph).

## Scenarios (Gherkin)

Criterios de aceptación en el caso de uso (fuente única):

- [`.claude/specs/backend/casos-de-uso/CU-BE-12-consulta-de-la-kb-desde-el-panel.md`](../../../specs/backend/casos-de-uso/CU-BE-12-consulta-de-la-kb-desde-el-panel.md)

Escenarios que materializa esta tarea, en su parte de adaptador (la traducción a 502 y su visibilidad
end-to-end son de `-06`/`-07`):

- *Un fallo del proveedor de embeddings no se disfraza de KB vacía* — el adaptador levanta `PortError`.
- *Un vector de dimensión inesperada se rechaza como fallo del proveedor* — hallazgo de
  `scenario-coverage`: es un modo de fallo **distinto** de "proveedor caído" (respuesta bien formada,
  datos incompatibles) y no lo cubría ningún escenario. Sin este assert, el vector inválido llegaría a
  la comparación pgvector y reventaría como error de driver, sin decir qué pasó.
- Camino feliz del puerto: `embed_query` devuelve un vector de la dimensión configurada. No estaba
  declarado como escenario, y `testing.md` exige que cada test derive 1:1 de uno.

## Provides

- `EmbeddingModel.embed_query` en el puerto: `-05` (retriever) puede depender de la firma.
- `OpenAIEmbeddingModel.embed_query` real, conmutable por `get_embedding_model(settings)`.
- `settings.rag_estado_weight` / `rag_search_window` / `rag_chunks_per_doc`: `-05` y `-06` los leen.

## Definition of Done

- [x] Tests escritos ANTES de la implementación (TDD) — Red → Green → Refactor
- [x] Cada escenario del CU que materializa esta tarea tiene al menos un test (camino feliz + bordes)
- [x] Todos los tests en verde (`make test`, sin regresión sobre los 1064)
- [x] Spec cumplida; lo declarado en `Provides` queda realmente disponible para las tareas dependientes
- [x] Lint / format / typecheck OK (`ruff`, `mypy --strict`) — cero secretos en código
- [x] Gate de mutation testing superado (`make mutation`, cosmic-ray `break: 80`) sobre los ficheros tocados
- [x] **Gate `sdd-lint` superado** — tras `mutation`, antes de `fact-checker`
- [x] Gate de `fact-checker` superado — antes de commit/resumen
- [x] **SDD** — sin cambios de spec/CU (los fijó `-01`); declararlo así en el session log
- [x] Documentación actualizada — tres capas:
  - [x] **Docstrings** — `embed_query` en puerto y adaptador; los tres settings nuevos
  - [x] **Doc técnica** — `.env.example` si documenta settings; `rag-ingestion.md` §5 si aplica
  - [x] **Histórico** — session log en `.claude/context/backend/backend-kb-retriever-03.md`

> ⚠️ **No solapar `pytest` con `cosmic-ray exec`**.
