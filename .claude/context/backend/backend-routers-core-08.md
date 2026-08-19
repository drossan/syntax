# Session log — backend-routers-core-08

Tarea: puerto `Storage` (nuevo) + adaptador filesystem local + extensión de `MessageRepository` para
adjuntos (`Attachment`) + router `messages` completo (hilo con filtro de visibilidad server-side,
subida/descarga de adjuntos). Depends_on: 07 (`done`).

## Entradas

- 2026-08-19 — Arranque. Movida de `pending/` a `active/`, `status: pending`→`status: active`.
- Pausa para pedir permiso antes de añadir `python-multipart` (dependencia nueva, requerida por
  FastAPI para `UploadFile`/multipart — el endpoint de subida ya estaba en el contrato desde antes de
  esta tarea, pero la dependencia runtime no estaba instalada). Owner: sí, añadirla.

## Resumen

`app/domain/ports/storage.py`: `Storage` (Protocol) con forma real (`save`/`get_url_or_path`) — antes
solo un docstring "GUIÓN". `app/infra/storage/local.py` (nuevo): `LocalFilesystemStorage` — valida que
la `key` no escape `root` (anti path-traversal) ANTES de tocar el filesystem, IO bloqueante vía
`asyncio.to_thread` (sin dependencia async de filesystem nueva). `app/domain/entities/business.py`:
entidad `Attachment` (nueva). `MessageRepository` (puerto + adaptador) gana `get`/`add_attachment`/
`get_attachment`, y `list_by_ticket` gana paginación real (`PageResult[Message]`, antes `list[Message]`
sin paginar) + filtro `visibilities` a nivel de query (no post-filtrado, para no romper `total`/
paginación cuando se ocultan mensajes `internal`). `Settings` gana `storage_root`/`max_upload_bytes`.
Router `messages.py`: los 4 endpoints del contrato (incl. el nuevo `GET .../attachments/{attachment_id}`,
añadido al contrato por esta tarea).

## Decisiones técnicas + porqué

- **Capacidad de escritura por RUNTIME, no fija en `Depends(require_capability(...))`**: `POST
  /tickets/{id}/messages`/`POST /messages/{id}/attachments` necesitan `ticket.reply` o
  `note.internal.write` según el `visibility` del mensaje (dato del payload/de la fila, no conocido en
  tiempo de definición de la ruta) — `require_capability` fija la capacidad al declarar el endpoint, así
  que no sirve aquí. Solución: abrir el scope con `ticket.read` (invariante de `rbac.md`: todo rol que
  escribe mensajes también lee tickets) y comprobar la capacidad de escritura/lectura específica a mano
  contra `subject.capabilities`, lanzando `AuthorizationDenied` igual que `require_capability` internamente.
- **`list_by_ticket` filtra `visibility` a nivel de QUERY, no post-filtrado en el router**: si el router
  paginara primero y descartara `internal` después, `page.total`/el número de `items` de una página
  quedarían inconsistentes para un subject sin `note.internal.read`. El puerto acepta
  `visibilities: list[MessageVisibility] | None` — el router resuelve `[public]` o `None` según la
  capacidad del subject, ANTES de llamar al repo.
- **Adjunto de 0 bytes se ACEPTA**: el Gherkin de la tarea deja el comportamiento como decisión
  explícita a tomar ("aceptado, o 422 — no un 500"); se eligió aceptar (un fichero vacío es un adjunto
  válido, aunque inusual) — no hay ningún spec que justifique rechazarlo.
- **413 vía `fastapi.HTTPException` directa, no una `DomainError` nueva**: no existe ninguna excepción
  de dominio para "payload demasiado grande" (las 5 `DomainError` cubren 404/409/422/502
  exclusivamente) y el proyecto ya soporta este patrón (`app.core.deps._unauthorized()` para 401) — el
  handler de `StarletteHTTPException` ya registrado en `main.py` lo traduce a problem+json sin más.
- **`key` de storage incluye el `attachment_id`** (`{tenant_id}/{message_id}/{attachment_id}-{filename}`):
  dos adjuntos con el mismo `filename` al mismo mensaje no colisionan en disco — el nombre de fichero
  del usuario nunca es, por sí solo, la clave real.
- **`GET /messages/{id}/attachments/{attachment_id}` comprueba `attachment.message_id != message.id`**:
  la URL nombra un `message_id` Y un `attachment_id` — un `attachment_id` real pero de OTRO mensaje debe
  dar 404 (nunca servir el contenido de un adjunto "vecino" solo porque el UUID es válido).

## Tests corridos + resultado

- `tests/test_storage_local.py` (nuevo, **7 tests**): roundtrip `save`/`get_url_or_path`, crea
  directorios intermedios, dos keys con el mismo `filename` no colisionan, rechazo de `..`/ruta
  absoluta (anti path-traversal, antes de tocar el filesystem), fallo de IO envuelto en `PortError`.
- `tests/test_repositories_ticket.py` (ampliado, **19 tests**): 3 tests nuevos de
  `add_attachment`/`get_attachment` (roundtrip, inexistente, dos adjuntos incluso con el mismo
  `filename` obtienen `storage_key` distinto), + ajuste de los tests de `list_by_ticket` a la nueva
  firma paginada (`PageResult`, no `list[Message]`).
- `tests/test_router_messages.py` (nuevo, **18 tests**): los 14 escenarios Gherkin de la tarea
  (filtro internal/paginación del hilo, capacidades de escritura por visibilidad, body vacío, subida/
  descarga, colisión de filename, límites 413/exacto/0-bytes, mensaje inexistente→404, fallo de
  `Storage.save()`→502) + refuerzos de mutación: `page_size` en sus límites exactos, `visibility`
  inválida→422, y un adjunto real descargado con el `message_id` de la URL equivocado→404 (aislamiento
  cross-mensaje, no solo cross-tenant).
- `tests/test_ticket_service.py`/`test_approval_service.py`: fakes de `MessageRepository`
  actualizados a la firma nueva (`list_by_ticket` paginado + `add_attachment`/`get_attachment`).
- Suite completa del backend (`pytest -q`): **587 tests, verde**, sin regresiones.
- `ruff check .`/`ruff format --check .`: OK. `mypy app` (strict): `Success: no issues found in 114
  source files`.
- Mutation (`cosmic-ray`, `--fail-over 20`):
  - `app/infra/storage/local.py`: **2.94%** → PASA directamente.
  - `app/api/v1/routers/messages.py`: primera pasada **18.46%** (Query bounds del hilo, `except
    ValueError` de `_parse_visibility` sin ejercitar, aislamiento cross-mensaje del adjunto sin
    probar) → refuerzos → **7.69%** → PASA.
- `/sdd-lint`: mecánico limpio (YAML del contrato sigue válido tras añadir el path nuevo). Semántico
  vía subagente fresco (**relanzado una vez** — la primera pasada murió por un error de conexión de la
  API a mitad de respuesta, sin producir veredicto; la segunda completó con normalidad): **0 ERROR, 2
  AVISO** — ambos con la misma raíz: `spec.md` no tiene ningún FR sobre adjuntos/`Storage`/límite de
  tamaño (la funcionalidad nace del contrato/la tarea, sin FR previo) y CU-BE-04 tampoco los menciona
  (fue escrito antes de que existiera el puerto `Storage`). Ninguno es una contradicción, ambos
  reconocidos como hueco de spec para un futuro FR.
- `fact-checker`: pendiente de lanzar tras este session log.

## Docs actualizadas

- `.claude/specs/general/api-contract.yaml`: nuevo path `GET /messages/{id}/attachments/{attachment_id}`
  (200 `application/octet-stream`/403/404); `POST /messages/{id}/attachments` gana las respuestas
  404/413/502 que le faltaban.
- `backend/requirements.in`/`requirements.txt`: `python-multipart` (autorizado por el owner).
- Docstrings de `app/domain/ports/storage.py` (por qué `key` la construye el llamante, no el
  adaptador), `app/infra/storage/local.py` (la defensa anti path-traversal, IO vía `to_thread`),
  `app/domain/ports/repositories.py` (`MessageRepository`, por qué `visibilities` filtra a nivel de
  query), `app/api/v1/routers/messages.py` (por qué la capacidad de escritura no puede ser fija en
  `require_capability`, por qué 0 bytes se acepta, por qué 413 es `HTTPException` directa). Este
  session log.

## Ficheros / commits

- `backend/app/domain/ports/storage.py` (contenido real), `backend/app/infra/storage/__init__.py`
  (nuevo), `backend/app/infra/storage/local.py` (nuevo), `backend/app/api/v1/routers/messages.py` (de
  esqueleto a código real), `backend/app/api/v1/schemas/messages.py` (nuevo).
- `backend/app/domain/entities/business.py` (`Attachment`), `backend/app/domain/ports/repositories.py`
  (`MessageRepository` ampliado), `backend/app/infra/db/repositories/message.py` (adaptador ampliado),
  `backend/app/core/config.py` (`storage_root`/`max_upload_bytes`), `backend/app/core/deps.py`
  (`get_storage`), `backend/app/main.py` (monta el router `messages`).
- `backend/requirements.in`/`requirements.txt` (`python-multipart`).
- `backend/tests/test_storage_local.py` (nuevo), `backend/tests/test_router_messages.py` (nuevo),
  `backend/tests/test_repositories_ticket.py` (ampliado), `backend/tests/test_ticket_service.py`/
  `test_approval_service.py` (fakes actualizados).
- `.claude/specs/general/api-contract.yaml` (path nuevo + respuestas que faltaban).
- `backend/cosmic-ray.toml` (apunta a `app/api/v1/routers/messages.py`, último módulo mutado).
- Commit: uno solo, `backend-routers-core-08: feat(backend): puerto Storage + filesystem local + router messages/attachments`.

## Tiempo real

- `estimate: 4h` → real: ampliada por la pausa de autorización de dependencia (`python-multipart`) y
  por el diseño de la autorización por-visibilidad en runtime (no cubierto por el mecanismo
  `require_capability` existente, tuvo que resolverse con `get_tenant_context` invocado directamente).

## Follow-ups

- Los 2 AVISO de `/sdd-lint` (ausencia de FR de adjuntos en `spec.md`/CU-BE-04) quedan como hueco de
  spec nombrado, no bloquean este cierre — candidato a un FR-04x futuro si se retoca `spec.md`.
- El primer intento del subagente semántico de `/sdd-lint` murió por un error de conexión de la API a
  mitad de respuesta (sin veredicto) — se relanzó una segunda vez, que completó con normalidad; anotado
  aquí como transparencia del proceso, no afecta al resultado final (0 ERROR, 2 AVISO).
