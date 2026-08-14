# Backend · Guía de implementación

La guía maestra completa vive en el repo: **`backend/IMPLEMENTATION-GUIDE.md`**. Es el punto de entrada
para construir el backend real desde el esqueleto. Cubre:

1. **Mapa de specs** (fuente de verdad).
2. **Orden de build** por bloques: tooling+specs → core → DB → LLM → dominio → routers → RAG → grafo →
   seeds → scheduler SLA (respetando dependencias).
3. **Cómo levantar**: `make install/migrate/ingest/seed/run`, `.env`, LangSmith, scheduler.
4. **Mapa de piezas** (hexagonal) + **ciclo HITL end-to-end**.
5. **Gate manual "OpenAPI generado ⊇ contrato"**.
6. **Avisos de riesgo** consolidados.
7. **Checklist de "esqueleto seguible"**.

## Avisos de riesgo (resumen)

::: danger Leer antes de implementar
1. **RLS footgun** — `SET app.tenant_id` en pool asyncpg reutiliza conexiones → fuga cross-tenant. Usar
   `SET LOCAL` / reset; aislamiento primario app-level; **tests de integración obligatorios**.
2. **HITL/checkpointer** — estado solo en checkpoint Postgres (reanudar tras reinicio); doble decisión →
   409 idempotente; `thread_id=ticket_{id}_run_{n}` (run nuevo por reapertura).
3. **Dimensión del vector** — cambiar `EMBEDDING_DIM` obliga a re-embeber todo + reconstruir índice.
4. **Prompt-injection** — el ticket es input no confiable; aislarlo del system-prompt; riesgo máximo con
   `auto_approve=true`.
5. **Fallo del LLM** — `AgentRun.failed` + error controlado; timeout/retry/backoff + 429 en el adaptador.
6. **Conformidad LangGraph/LangChain** — `requirements.txt` es un stub; pinar el surface (`interrupt`,
   `with_structured_output`, `PostgresSaver`, `add_messages`, `trim_messages`, `@tool`) al implementar.
:::

## Pendiente al implementar

- Compilar el lockfile (`requirements.txt` es un stub) y pinar las versiones de LangGraph/LangChain.
- Tests de integración de RLS y del ciclo HITL (reinicio + concurrencia).
- Añadir `openapi-spec-validator` para un gate formal del contrato.
