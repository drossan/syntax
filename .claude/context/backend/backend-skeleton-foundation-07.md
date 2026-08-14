# Session log — backend-skeleton-foundation-07 (Skeleton core + app factory + healthcheck)

## 2026-08-13 — Arranque

**Estado:** tarea movida `pending → active` (`status: active`, `updated: 2026-08-13`). Dep 01 `done`.
Doc-only skeleton (ficheros + guión, sin lógica de negocio).

**Aviso de alcance (una frase):** materializo `config.py`/`security.py`/`logging.py`/`deps.py`/`main.py`
como **ficheros de esqueleto con guión docstring** (mismo patrón que los `__init__.py` de la 01), **sin
implementación** ni imports de deps no instaladas (evita romper `compileall` y no adelanta código que el
owner construye a mano).

**Verificaciones previas (esta sesión):**
- `app/core/__init__.py` ya trae el guión-puntero (contrato `get_settings()`/`create_app()`,
  anti-patrones). Los ficheros nuevos lo desarrollan por módulo.
- `backend/.env.example`: nombres reales de vars → `APP_ENV`, `DATABASE_URL` (asyncpg), `JWT_SECRET/
  ALGORITHM/ACCESS_TTL/REFRESH_TTL`, `OPENAI_API_KEY`, `CHAT_MODEL`, `EMBEDDING_MODEL`, `EMBEDDING_DIM`
  (1536), `LANGSMITH_*`, y comentados `LOGIN_MAX_ATTEMPTS/WINDOW_SECONDS`, `AI_DRAFT_MAX_PER_TICKET` (B.1).
- `app/api/v1/__init__.py` fija el guión de routers (11 core / 12 flujo-IA) → `main.py` los monta.

## 2026-08-13 — Cierre

**Resumen:** Creados 5 ficheros de esqueleto (guión docstring, sin lógica) en `backend/app/`:
`core/config.py` (Settings BaseSettings + `get_settings()` `@lru_cache`, sin efectos en import),
`core/security.py` (Argon2id, JWT access sin capacidades, refresh contra `refresh_session` con rotación
+ reuse-detection por `family_id` + logout server-side, tokens de un solo uso reset/invitación),
`core/logging.py` (logging estructurado + request-id por `contextvar` + hook errores), `core/deps.py`
(sesión DB con `SET app.tenant_id`, `get_tenant_context`, `get_current_subject` que resuelve capacidades
**server-side por request** A1.7, `require_capability`→403), `main.py` (`create_app()`, middleware
request-id/CORS/throttling B.1, routers 11/12 placeholder, `/health/live`+`/health/ready` DB+pgvector,
`/metrics`).

**Decisiones técnicas + porqué:**
- **Ficheros guión-only** (no stubs con firmas): mismo patrón que los `__init__.py` de 01; el owner lo
  construye a mano (goal del plan); evita imports de deps no instaladas y no adelanta código.
- Guiones cargan los **refuerzos**: throttling login/refresh, /health split liveness/readiness,
  reuse-detection + logout server-side, capacidades server-side por request, observabilidad de errores +
  /metrics.

**Verificación en sesión (bucle principal):** `python3 -m compileall -q` sobre los 5 → exit 0.

**Verificación (gate `fact-checker`, subagente fresco, sonnet por config):** **8/8 VERIFICADO**, 0
INCORRECTO, 0 NO VERIFICABLE. Cubrió: existencia de los 5 (E1), que son solo docstring sin código
ejecutable (E2, grep sin coincidencias de import/def/class/=), compileall exit 0 (E3), guión config
prohíbe efectos en import + BaseSettings/get_settings (E4), env vars ∈ `.env.example` (E5), security
Argon2/JWT-sin-caps/refresh contra `refresh_session` que existe en 03 (E6), main create_app+request-id+
health DB/pgvector (E7), deps capacidades server-side + tenant + 403 (E8).

**Docs:** 5 ficheros nuevos en `backend/app/`. Plan: `[x]` tarea 07 + Registro.

**Ficheros/commits:** `backend/app/core/{config,security,logging,deps}.py` + `backend/app/main.py`
(nuevos); task 07 pending→active→completed; session log; plan. (Commit pendiente de que el owner lo pida.)

**Tiempo real:** ~0.75 h.

**Follow-ups:** 08 (DB session/repos/RLS) cuelga de core+data-model; 09 (LLM/embeddings/LangSmith) de
core; 10/11/12 usan `deps.py` (autorización/tenant). Al implementar: el `SET app.tenant_id` en pool
asyncpg es footgun → tests de integración (08).
