---
id: backend-executable-foundation
package: backend
status: active
branch: plan/backend/executable-foundation
created: 2026-08-14
updated: 2026-08-15
---

# Backend — Cimientos ejecutables (entorno · config · seguridad · logging · app factory · /health)

## Contexto y problema

El backend de Syntax es hoy un **esqueleto doc-only completado** (plan `skeleton-foundation`, 19 tareas):
layout hexagonal, 79 módulos con guión, specs coherentes (EARS + 10 CUs + data-model + rbac + agent-graph
+ rag-ingestion), contrato OpenAPI 3.1, ADRs, `Makefile` y seeds. **No hay código de negocio ejecutable**:
`requirements.txt` es un stub (deps sin compilar/instalar) y `make test` no corre.

La transición a **Fase 2 (código real, TDD)** ya está sancionada: `.claude/task-pipeline.yml` activó hoy
(2026-08-14) `stack.packages.backend` → `pytest` + `mutmut`, el `HOW-TO-START-A-TASK.md` del backend lo
declara, y hay commit de transición. Falta arrancar. Este es el **primer plan** de la Fase 2.

Es imposible escribir el primer test mientras el entorno no ejecute. Este plan cubre el bloque de
**cimientos** del build-order (`backend/IMPLEMENTATION-GUIDE.md` §2, bloque 2): dejar el entorno ejecutable
y construir las **primitivas transversales sin estado** — settings inyectables, hashing/JWT, logging con
request-id, app factory y `/health/live` — sobre las que se apoyan todas las capas siguientes.

> **Modo de trabajo acordado** (2026-08-14): el **código lo escribe el owner**; yo (asistente) redacto
> tareas/escenarios, guío paso a paso, **propongo diffs concretos** cuando ayude, reviso lo escrito, redacto
> la **documentación (specs/ADRs/session log)** y corro los gates (mutation/sdd-lint/fact-checker). Reparto
> **híbrido, decidido sobre la marcha** (guío ↔ propongo diff); la última palabra sobre el código es del owner.

> **Roadmap de planes del backend** (contexto, no alcance de este plan). Este plan es el 1.º; los
> siguientes seguirán el build-order de la guía: **(2)** capa DB + RLS + `/health/ready` + alias `/health`
> (footgun `SET app.tenant_id`, migraciones reales) · **(3)** puerto LLM + tracing LangSmith · **(4)** dominio
> (servicios + puertos) · **(5)** routers core + flujo-IA (gate OpenAPI ⊇ contrato) · **(6)** RAG
> (ingestión + retriever) · **(7)** agente LangGraph + checkpointer/HITL · **(8)** seeds + scheduler SLA.
> Cada uno será su propio `/plan-task`.

## Objetivos

1. **Entorno backend ejecutable y reproducible.**
   - *Criterio de éxito*: en un clon limpio, `make install` compila **ambos** lockfiles (dev constreñido
     contra runtime, versiones compartidas) e instala; `docker compose up -d db` deja Postgres+pgvector sano;
     y `make test` queda **verde** (colecta y ejecuta un smoke mínimo) sin errores de entorno.

2. **Configuración por entorno inyectable, sin efectos en import.**
   - *Criterio de éxito*: `get_settings()` devuelve `Settings` cacheada; importar `app.core.config` no
     lee entorno ni crea clientes; un test inyecta settings falsos sin tocar `.env`.

3. **Primitivas de seguridad sin estado verificadas.**
   - *Criterio de éxito*: `hash_password`/`verify_password` (Argon2id) y `create_access_token`/
     `decode_access_token` (JWT HS256, `exp`, **sin capacidades en el token**) con tests de firma
     válida/inválida y expiración.

4. **Observabilidad transversal: logging estructurado con request-id correlacionable.**
   - *Criterio de éxito*: cada log de una request comparte un id (via `structlog`); el middleware lee
     `X-Request-ID` entrante o genera uno, y lo devuelve en la respuesta; `get_request_id()` disponible.

5. **App factory testeable y liveness fiable.**
   - *Criterio de éxito*: `create_app()` valida settings, monta logging/request-id/CORS y los handlers de
     error **problem+json** (`{type,title,status,detail,errors[]}`); `GET /health/live` → 200 sin tocar
     dependencias; una ruta desconocida devuelve el envelope de error del contrato.

## Alcance y fuera de alcance

### Dentro del alcance
- **Entorno ejecutable (tarea 01, verificación, no-TDD)**: actualizar `make install` para compilar **ambos**
  lockfiles reproducibles (`pip-compile requirements.in -o requirements.txt`, luego `requirements-dev.in ->
  requirements-dev.txt` **con `-c requirements.txt`**); **añadir `structlog`** a `requirements.in` (runtime) y
  **`mutmut` + `pip-tools`** a `requirements-dev.in`; instalar en `.venv`; `.env` desde el ejemplo; `docker
  compose up -d db` sano; **smoke-import** de las pesadas (`fastapi, pydantic, structlog, langgraph,
  langchain`); **pinar `mutmut`**, añadir `[tool.mutmut]` a `pyproject.toml`, confirmar CLI/versión y
  **registrar la invocación exacta** (`mutmut run`/`results`) — el plugin marca el camino mutmut como "no
  verificado" (F3), así que se sanea aquí.
- **Scaffold de tests + ADRs (tarea 02, docs/scaffold)**: crear `backend/tests/` + `conftest.py` + **smoke
  test** (carve-out testing.md §1) → `make test` verde; **ADR-0013** (arranque Fase 2, supersede 0012) +
  actualizar `adr-index.md`; **nota en ADR-0001** (el flujo `dev→main` no se adoptó; trunk-from-`main` de facto).
- `app/core/config.py` (tarea 03): `Settings(BaseSettings)` con los campos de `.env.example` + **`CORS_ORIGINS`**
  + `get_settings()` (lru_cache), sin efectos en import.
- `app/core/security.py` (tarea 04, **una sola tarea**): hashing Argon2id (`hash_password`/`verify_password`)
  **+** JWT access (`create_access_token`/`decode_access_token`, `exp`, sin capacidades). **Primitivas puras**
  (secret/algorithm/ttl/now **por parámetro**; el wiring a `get_settings()` es del plan de auth). `decode` fija
  `algorithms=[algorithm]` (rechaza `alg=none`/confusión). Dos grupos de escenarios.
- `app/core/logging.py` (tarea 05): `configure_logging(settings)` con **`structlog`** (JSON en prod, legible en
  dev) + request-id (`contextvar` + middleware) + `get_request_id()`; **ADR-0015** (observabilidad/structlog).
- `app/main.py` (tarea 06): `create_app()` factory + middleware (request-id, **CORS**) + handlers de error
  problem+json (**404/405/422 con `errors[]`/500**, con **i18n por `Accept-Language`** — NFR-007) + `GET
  /health/live`; documentar que `/health/ready` + alias `/health` llegan en el plan de capa DB.

### Fuera de alcance
- **Refresh tokens, rotación, reuse-detection, `logout` server-side y `auth_token` de un solo uso**
  (necesitan la tabla `refresh_session`/`auth_token` de la capa DB) → plan de **auth**, posterior a la capa DB.
- **`/health/ready` y el alias `/health`** (comprueban DB alcanzable + extensión pgvector): requieren el
  engine/sesión DB → **plan de capa DB (08)**. No se entrega un `ready` verde falso (anti-patrón del guión).
- **Aviso (F2)**: el servicio **`api`** de `docker-compose.yml` y su `HEALTHCHECK` (que apunta a `/health`,
  Dockerfile L50-51) quedan **rojos** hasta que el plan de capa DB entregue `/health`. Este plan solo promete
  `docker compose up -d db`. El `requirements.txt` runtime que compila la 01 no tiene consumidor en Docker (el
  builder recompila desde `requirements.in`, Dockerfile L27) — se mantiene por reproducibilidad local (F1).
- **`app/core/deps.py` real** (`get_db_session`, `get_tenant_context`+`SET app.tenant_id`, `get_current_subject`
  con caps server-side, `require_capability`): dependen de DB (08) + dominio/RBAC (10) → planes posteriores.
- **Throttling de `/auth/login|refresh`** y **`/metrics`**: no hay endpoints de auth ni superficie de métricas
  aún → planes posteriores (routers / observabilidad).
- **Verificación profunda del surface de LangGraph/LangChain** (`interrupt()`, `Command(resume=)`,
  `with_structured_output`, `PostgresSaver`): aquí solo se confirma que **importan**; el pin/verificación de
  firmas concretas se hace en el **plan del agente** (donde se usan).
- **Migraciones reales / RLS**, ingestión, seeds, routers, dominio, agente: planes posteriores del roadmap.

## Recursos externos

- Guía de implementación: `backend/IMPLEMENTATION-GUIDE.md` (§2 build-order, §3 entorno, §6 avisos de riesgo).
- Specs: `.claude/specs/backend/spec.md` (EARS — anclas: FR-001, FR-005/A1.7, FR-008, NFR-001, NFR-003, NFR-004),
  guiones de `app/core/*.py` y `app/main.py`, `.claude/specs/general/api-contract.md` (envelope problem+json,
  RFC 9457), `.claude/specs/general/testing.md` (§1 carve-out smoke, §4 niveles backend, §5 determinismo),
  `.claude/specs/general/coding-standards.md`. Casos de uso que **consumen** las primitivas de la tarea 04:
  `casos-de-uso/CU-BE-01` (login → access) y `CU-BE-02` (fijar contraseña Argon2id).
- ADRs: 0001 (git flow — nota F8), 0003 (SPA), 0004 (auth JWT — refresh/rotación fuera de alcance aquí),
  **0012** (fase 1 doc-only → **superado por ADR-0013**, tarea 02). ADR-0015 (structlog) en la tarea 05.
- Config del pipeline: `mode: full`, backend `pytest`+`mutmut`+`break:80` (**camino mutmut marcado "no
  verificado" por el plugin → se sanea en la tarea 01**), **SDD on**, git-automation (auto-commit al cerrar
  tarea, auto-pr al cerrar plan), fact-checker en `sonnet`.

## Estimación global

- **Tareas totales**: 6 (01 entorno no-TDD + 02 scaffold/docs + 4 TDD: config, security, logging, factory).
- **Esfuerzo estimado**: ~3–4 sesiones (tras endurecer escenarios, 03–06 crecieron). Riesgo concentrado en
  la 01 (compilar por primera vez el árbol completo — langchain/langgraph/argon2-cffi/asyncpg/pgvector
  nativos — puede dar fricción de versiones).
- **Recursos**: owner (código) + asistente (tareas/gates/docs/ADRs); Docker local; sin credenciales cloud (no
  se necesita OpenAI/LangSmith real para estos cimientos).

## Criterios de calidad y verificación

- **TDD** en las 4 tareas de código (03–06): test rojo 1:1 del Gherkin **antes** de implementar. La tarea 01
  (entorno) y la 02 (scaffold+ADR) son **verificación/docs**, no TDD; el smoke de la 02 entra por el
  **carve-out** de testing.md §1. Sin gate de mutation en 01/02 (no hay código de producción propio).
- **Niveles de test** (testing.md §4 / HOW-TO): config, security (hashing/JWT) y logging → **unit**; app factory
  + `/health/live` → **integración** vía `httpx.ASGITransport` (arranca la app en proceso, sin servidor). Sin
  infra DB (fuera de alcance).
- **Gates de cierre por tarea de código** (03–06): `make test` verde · `ruff check` + `ruff format --check` ·
  `mypy` **strict** · **mutation `mutmut` (`break: 80`)** sobre los ficheros tocados · **`/sdd-lint`** ·
  **`fact-checker`**. El **primer** run end-to-end de survivors cae en la 03 (primer código) como *shakeout* del
  toolchain mutmut ya pinado/configurado en la 01; si mutmut resulta inviable sobre este código, **parar y
  avisar** (la herramienta es decisión de config, no se improvisa).
- **Determinismo** (testing.md §5): sin depender de reloj/entorno reales; settings inyectados en los tests.
- **SDD** (matiz F7): 03/05/06 son **infra pura sin CU de actor** → Gherkin **local** declarando "sin cambios de
  spec/CU". La **tarea 04** también lleva Gherkin local (round-trips unitarios, no 1:1-testables en un CU que
  necesita DB/endpoints), pero **traza explícita** a FR-001/FR-008 y a **CU-BE-01/CU-BE-02** como flujos
  consumidores (no se fuerza enlace 1:1). Verificado que `sdd-lint` **no bloquea** Gherkin local (no hay chequeo
  tarea→CU); la traza preempta un posible AVISO semántico. No se inventan CUs para primitivas de infra.
- **Hexagonal**: `app.domain` no importa `app.infra`/`app.api`; settings inyectables; cero secretos en código.

## Tasks

- [x] `backend-executable-foundation-01` (P1) — Entorno ejecutable: lockfiles (`make install` compila ambos, dev `-c`) + deps (structlog/mutmut/pip-tools) + docker db + smoke-import + pin/verificar mutmut  · depends_on: —  · **done 2026-08-15**
- [x] `backend-executable-foundation-02` (P1) — Scaffold tests + smoke + ADR-0013 (supersede 0012) + adr-index + nota ADR-0001  · depends_on: backend-executable-foundation-01  · **done 2026-08-15**
- [x] `backend-executable-foundation-03` (P1) — Settings inyectables + `CORS_ORIGINS` (`app/core/config.py`)  · depends_on: backend-executable-foundation-02  · **done 2026-08-15**
- [x] `backend-executable-foundation-04` (P1) — Primitivas de seguridad sin estado: Argon2id + JWT access (`app/core/security.py`)  · depends_on: backend-executable-foundation-02  · **done 2026-08-15**
- [ ] `backend-executable-foundation-05` (P1) — Logging estructurado (`structlog`) + request-id + ADR-0015 (`app/core/logging.py`)  · depends_on: backend-executable-foundation-03
- [ ] `backend-executable-foundation-06` (P1) — App factory + `/health/live` + CORS + envelope problem+json (`app/main.py`)  · depends_on: backend-executable-foundation-03, backend-executable-foundation-05

> Orden sugerido: **01** → **02** → (**03**, **04**) → **05** → **06**. Una sola tarea `active` por plan
> (comparten rama). El Gherkin definitivo de cada tarea se materializa tras la aprobación del plan (Paso 5 de
> `/plan-task`) y se endurece con `scenario-coverage`.

## Notas de arranque

- **Rama**: crear `plan/backend/executable-foundation` **desde `main`** (convención de facto del repo; no hay
  `dev` — decidido en grilling 2026-08-14; ADR-0001 se anota en la tarea 02, F8).
- **ADRs** (los redacta el asistente, el owner revisa): 0013 (arranque Fase 2, supersede 0012) en la tarea 02;
  0015 (structlog/observabilidad) en la tarea 05.

## Registro de cambios del plan

- 2026-08-14: creado (draft para aprobación).
- 2026-08-14: refinado con `grilling` (9 preguntas, 9 decisiones). Cambios: +`structlog` (runtime dep, ADR-0015);
  +`pip-tools`/`mutmut` en dev; **CORS incluido ya** (+ setting `CORS_ORIGINS`); **seguridad partida** en 2 tareas;
  `/health/ready` **diferido** (solo `/health/live`); precondición = full-install + smoke-import; rama **desde
  `main`**; **ADR-0013** (arranque Fase 2, supersede 0012); scaffold `tests/` + smoke (carve-out) para `make test`
  verde; tarea de entorno sin gate TDD/mutation.
- 2026-08-14: refinado con `design-review` (subagente opus; 8 hallazgos). Decisiones del owner:
  **F1** `make install` compila **ambos** lockfiles (dev `-c requirements.txt`) — reproducibilidad;
  **F4** tarea de entorno **partida** en 01 (entorno) + 02 (scaffold+ADR) para aislar la fricción de versiones;
  **F5** seguridad **fusionada** de nuevo en una sola tarea (04) — evita doble ceremonia de cierre sobre el mismo
  fichero (revierte la Q5 de grilling, con el nuevo argumento del reviewer);
  **F6** hashing/JWT **se mantienen** en cimientos (auth queda enfocado) + traza a CU-BE-01/02;
  **F2** aviso: servicio `api`/`HEALTHCHECK` rojos hasta el plan de DB (verificado en Dockerfile L50-51);
  **F3** mutmut (camino "no verificado" del plugin) se **pina + configura + verifica CLI** en la 01, primer run
  e2e en la 03 como shakeout, contingencia si es inviable;
  **F7** matiz SDD: 03/05/06 infra pura sin CU; 04 con traza a CU-BE-01/02 (Gherkin local igualmente válido);
  **F8** nota en ADR-0001 (dev nunca adoptado). Neto: **6 tareas** (01,02 no-TDD + 03–06 TDD).
- 2026-08-14: endurecido con `scenario-coverage` (subagente QA sonnet, 8 dimensiones). **(A) dentro de alcance**:
  incorporados escenarios a 03 (tipo inválido, `extra=ignore`, defaults/override B.1, CORS ausente/vacío/
  espacios/duplicados, fixture reset de `lru_cache`), 04 (**`alg=none`**/confusión de algoritmo, JWT malformado,
  claims requeridos, `exp==now+ttl` positivo, frontera de expiración, `verify_password` fail-closed, pass vacía),
  05 (concurrencia async, idempotencia de `configure_logging`, `APP_ENV=test`, saneo CRLF/gigante/vacío del
  `X-Request-ID`, reset del contextvar), 06 (**422 con `errors[]`**, 500, request-id en errores, settings
  inválidas, 404/405 limpios, correlación e2e log↔header). **Decisiones del owner** sobre huecos de requisito:
  **i18n `Accept-Language`** del envelope → **incorporado ya** a la 06 (NFR-007); **política de contraseña** →
  **diferida** al plan de auth (primitiva pura); **diseño JWT** → **puras con parámetros explícitos** (resuelve
  el wiring 03↔04). **(B) fuera de alcance**: todos consistentes con el plan (refresh/reuse/logout, throttling,
  `/health/ready`, `deps.py`, `/metrics`, RLS, verificación LangGraph) → **mantenidos diferidos** a sus planes.
- 2026-08-15: tarea **04 done** (`app/core/security.py`): Argon2id (`hash_password`/`verify_password` fail-closed)
  + JWT access puro (`create_access_token`/`decode_access_token`, `algorithms=[algorithm]`, `exp` manual vs `now`
  inyectado). 22 tests TDD; suite 41 passed; ruff+mypy strict; **cosmic-ray survival 0.00%** (2 supervivientes
  del `*` keyword-only → matados con 2 tests de contrato); sdd-lint sin ERROR; fact-checker 8/8. Traza a
  FR-001/FR-008 + CU-BE-01/02. Política de contraseña diferida al plan de auth.
- 2026-08-15: en la tarea 03, el gate de mutation `mutmut` **no puntuó** el código pydantic (no instrumenta
  funciones decoradas ni campos de clase; F3 materializado). Tras spike + evaluación, **se adopta `cosmic-ray`**
  como herramienta de mutation del backend (**ADR-0014**): `stack.packages.backend.mutation-tool: cosmic-ray`
  + `mutation-command: "make mutation"`; config en `backend/cosmic-ray.toml`; `mutmut` retirado. `config.py`
  puntuó **91.7%** (1 mutante equivalente documentado). La ADR de structlog se renumeró **0014→0015**.
