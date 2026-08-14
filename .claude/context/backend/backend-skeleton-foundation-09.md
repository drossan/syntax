# Session log — backend-skeleton-foundation-09 (Skeleton puerto LLM + embeddings + LangSmith)

## 2026-08-13 — Arranque

**Estado:** tarea movida `pending → active` (`status: active`, `updated: 2026-08-13`). Dep 07 `done`.
Doc-only skeleton (ficheros + guión).

**Avisos de alcance / honestidad (una frase c/u):**
- `.env.example` fija `CHAT_MODEL=gpt-4o-mini`; la tarea dice "gpt-4o/4.1 default" → el guión referencia
  `settings.CHAT_MODEL` (env), **no** hardcodea el modelo (evita contradecir la config real).
- La tarea pide conmutar por `LLM_PROVIDER` (no presente en `.env.example`) → **añado la línea
  `LLM_PROVIDER=openai`** a `.env.example` (directamente implícito por "conmutable por env").
- `with_structured_output` es API moderna de LangChain: mantengo la **nota de conformidad de 05** (deps
  LLM sin instalar/compilar → surface a pinar/verificar al implementar 15).

Ficheros a crear (4): `app/domain/ports/llm.py` (ChatModel + EmbeddingModel), `app/infra/llm/openai_adapter.py`
(adaptador OpenAI, lazy, sin creds en import, conmutable `LLM_PROVIDER`, timeout/retry/backoff+429→failed),
`app/infra/llm/structured.py` (helper `with_structured_output` para el clasificador de 05),
`app/infra/langsmith/tracing.py` (activación por env + obtención de `langsmith_trace_url` para AgentRun).

## 2026-08-13 — Cierre

**Resumen:** Creados 4 ficheros de esqueleto (guión) + 1 línea de env:
`app/domain/ports/llm.py` (puertos `ChatModel` [generate/grade/classify] + `EmbeddingModel`
[embed_documents/embed_query], dimensión desde `settings.EMBEDDING_DIM`),
`app/infra/llm/openai_adapter.py` (adaptador OpenAI único; lazy/sin creds en import; conmutable por
`LLM_PROVIDER`; `settings.CHAT_MODEL` no hardcodeado; timeout/retry/backoff + 429→`AgentRun.failed` A1.4),
`app/infra/llm/structured.py` (helper `with_structured_output` para el clasificador de 05 + nota de
conformidad de API), `app/infra/langsmith/tracing.py` (activación por env + `langsmith_trace_url`→AgentRun
+ degradación limpia). Añadido `LLM_PROVIDER=openai` a `.env.example`.

**Decisiones/avisos:**
- No hardcodear el modelo: guión referencia `settings.CHAT_MODEL` (default real `.env.example`=gpt-4o-mini,
  no el "gpt-4o/4.1" que citaba la tarea).
- Añadí `LLM_PROVIDER` a `.env.example` (implícito por "conmutable por env"; era el único gap).
- `with_structured_output`: mantengo la nota de conformidad de 05 (deps LLM sin instalar → surface a
  pinar/verificar al implementar).

**Verificación en sesión (bucle principal):** `compileall` exit 0; grep de líneas de código en los 4 →
sin coincidencias (solo docstring).

**Verificación (gate `fact-checker`, subagente fresco, sonnet por config):** **8/8 VERIFICADO**, 0
INCORRECTO, 0 NO VERIFICABLE. Cubrió existencia (G1), solo-docstring (G2), compileall (G3), puertos
ChatModel/EmbeddingModel (G4), adaptador lazy+LLM_PROVIDER+CHAT_MODEL+resiliencia (G5), structured+nota
honestidad (G6), tracing env+trace_url+degradación (G7), `LLM_PROVIDER` añadido + `CHAT_MODEL=gpt-4o-mini` (G8).

**Docs:** 4 ficheros nuevos + `.env.example` (M). Plan: `[x]` tarea 09 + Registro.

**Ficheros/commits:** `backend/app/domain/ports/llm.py`, `backend/app/infra/llm/{openai_adapter,structured}.py`,
`backend/app/infra/langsmith/tracing.py` (nuevos) + `backend/.env.example` (M); task 09
pending→active→completed; session log; plan. (Commit pendiente de que el owner lo pida.)

**Tiempo real:** ~0.5 h.

**Follow-ups:** 10 (servicios de dominio) usa `domain/ports`; 13 (ingestión) usa EmbeddingModel + vector;
14 (retriever) usa grade; 15 (grafo) usa generate/classify (structured). Al implementar: pinar surface
de LangChain/LangSmith al compilar el lockfile.
