# Session log — backend-skeleton-foundation-10 (Skeleton servicios de dominio + ports)

## 2026-08-13 — Arranque

**Estado:** tarea movida `pending → active` (`status: active`, `updated: 2026-08-13`). Deps 03 + 07
`done`. Doc-only skeleton. El dominio es el centro hexagonal: depende de puertos+entidades (03), **NO** de
routers/FastAPI.

**Aviso de alcance (una frase):** creo los 5 servicios nombrados (ticket/approval/rbac/notification/
classification) + `auth_service` (B.3 reset/invitación) y las 4 puertas que la tarea lista y aún faltan
(`vector`, `storage`, `email`, `clock`); `repositories.py` (08) y `llm.py` (09) ya existen.

**Verificaciones previas (esta sesión):** `app/domain/__init__.py` y `app/domain/ports/__init__.py`
fijan el guión (servicios + puertos por inyección, sin importar infra). rbac (02), data-model (03),
agent-graph (05) leídas esta sesión → base de `authorize()`, máquina de estados del ticket, y el eslabón
draft-aprobado→Message(public)+transición (A1.1).

Ficheros a crear (11): `services/__init__.py`, `services/{ticket,approval,rbac,notification,auth}_service.py`,
`services/classification.py`; ports `vector.py`, `storage.py`, `email.py`, `clock.py`.

## 2026-08-13 — Cierre

**Resumen:** Creados 11 ficheros de esqueleto (guión) del dominio en `backend/app/domain/`:
- **Servicios** (`services/`): `ticket_service` (máquina de estados de 6 estados + asignación + SLA +
  auditoría), `approval_service` (cola HITL, `auto_approve` por tenant default false, aprobar/editar→
  `Message(public)`+transición A1.1, rechazar, idempotencia→409), `rbac_service` (`authorize` por
  capacidad+ámbito, deny-all fail-closed, roles custom, caps server-side), `notification_service` (in-app
  + polling), `classification` (Classification structured output 1-de-17 + fallback), `auth_service`
  (login/refresh rotación+reuse-detection+logout, reset/invitación B.3 con email stub) + `__init__`.
- **Puertos** (`ports/`): `vector` (retrieval pgvector, upsert idempotente + search), `storage`
  (adjuntos, S3 diferido), `email` (stub B.3), `clock` (tiempo inyectable, testabilidad SLA/expiración).

**Decisiones/alcance:** creé los 5 servicios nombrados + `auth_service` (B.3) + las 4 puertas que la tarea
lista y faltaban; `repositories.py` (08) y `llm.py` (09) ya existían. Hexagonal estricto: 0 imports de
`app.infra`/`fastapi`/`sqlalchemy`/`openai`/`langchain` (solo referencias en prosa a dónde vive el
adaptador).

**Verificación en sesión (bucle principal):** `compileall` exit 0; grep de código ejecutable → sin
coincidencias (solo docstrings). Nota: primeros intentos de grep/compileall con listas de ficheros en
variable fallaron por word-splitting de zsh (args rotos); repetidos con lista explícita → válidos.

**Verificación (gate `fact-checker`, subagente fresco, sonnet por config):** **8/8 VERIFICADO**, 0
INCORRECTO, 0 NO VERIFICABLE. Cubrió existencia (H1), solo-docstring (H2), compileall (H3), sin imports de
infra/API (H4), rbac authorize capacidad+ámbito+deny-all == 02 (H5), máquina de estados == 03 (H6),
approval auto_approve=false + Message(public) + 409 (H7), classification 1-de-17 structured + auth B.3 (H8).

**Docs:** 11 ficheros nuevos. Plan: `[x]` tarea 10 + Registro.

**Ficheros/commits:** `backend/app/domain/services/{__init__,ticket_service,approval_service,rbac_service,
notification_service,classification,auth_service}.py` + `backend/app/domain/ports/{vector,storage,email,
clock}.py` (nuevos); task 10 pending→active→completed; session log; plan. (Commit pendiente de que el
owner lo pida.)

**Tiempo real:** ~1 h.

**Follow-ups:** 11 (routers core) y 12 (routers flujo-IA) invocan estos servicios (deps 06/07/10); 16
(HITL) usa `approval_service`; 18 (scheduler SLA) usa `ticket_service`+`clock`. Adaptadores de los puertos
nuevos (storage/email/clock) se materializan al implementar; email real diferido.
