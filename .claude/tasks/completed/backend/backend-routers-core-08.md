---
id: backend-routers-core-08
package: backend
plan: routers-core
status: done
priority: 2
depends_on: [backend-routers-core-07]
estimate: 4h
actual: 5h
issue:
created: 2026-08-19
updated: 2026-08-19
---

# MessageRepository + puerto Storage (nuevo) + adaptador filesystem local + router messages

## Description

Mensajes de ticket (hilo, visibilidad `public`/`internal`) + adjuntos. Nace el puerto `Storage`
(binario fuera de Postgres) con un adaptador a **filesystem local** (decisión de `grilling`: sin nube en
esta fase). Spec: CU-BE-04 (parte de mensajes), `api-contract.yaml` (`messages`, `attachments`).

## Spec

- **`app/domain/ports/storage.py`** (nuevo): `Storage` (Protocol, async): `save(key: str, content:
  bytes, content_type: str) -> None`, `get_url_or_path(key: str) -> str` (para servir el adjunto).
  Firma en tipos de dominio, sin exponer detalles de filesystem (ruta absoluta, permisos) al router.
- **`app/infra/storage/local.py`** (nuevo): adaptador `LocalFilesystemStorage` — guarda bajo un directorio
  raíz configurable (`settings.storage_root` o similar, nuevo en `Settings`), `key` = ruta relativa
  determinista **incluyendo un identificador único del adjunto** (p.ej. `{tenant_id}/{message_id}/
  {attachment_id}-{filename}`, no solo `filename` — dos adjuntos con el mismo nombre de fichero al mismo
  mensaje NO deben colisionar en disco, hallazgo de `scenario-coverage`); valida que la ruta resultante no
  escape el directorio raíz (anti path-traversal — rechaza `key` con `..`). Un fallo de IO (disco lleno,
  permisos) se envuelve en `PortError`, nunca una excepción de filesystem cruda.
- **`app/infra/db/repositories/message.py`**: adaptador de `MessageRepository` sobre `BaseRepository[
  Message]` + `Attachment` (join simple por `message_id`).
- **Router `messages.py`**:
  - `GET /tickets/{id}/messages` (`ticket.read`) → hilo paginado (`page`/`page_size`, contrato), ordenado
    `created_at asc`; los `internal` se filtran server-side si el subject no tiene `note.internal.read`.
  - `POST /tickets/{id}/messages` (`ticket.reply` para `public`, `note.internal.write` para `internal`) →
    `Message` nuevo; `body` vacío se rechaza (422).
  - `POST /messages/{id}/attachments` (multipart, misma capacidad que el mensaje al que se adjunta) →
    guarda vía `Storage.save`, persiste `Attachment{filename, content_type, size_bytes, storage_key}`.
    `message_id` inexistente → 404.
  - **`GET /messages/{id}/attachments/{attachment_id}`** (nuevo — sin él, un adjunto subido nunca se podía
    recuperar por HTTP, hallazgo de `scenario-coverage`; ampliación del contrato compartido) → misma
    capacidad de lectura que el mensaje; sirve el contenido vía `Storage.get_url_or_path`/streaming.
  - Límite de tamaño: rechazo explícito (413) por encima de un máximo configurable (p.ej. 10 MB) — no se
    acepta un adjunto sin límite; el límite exacto (`== max`) se acepta, solo se rechaza por encima.

## Fuera de alcance

- Adaptador de storage en nube (S3/GCS) → diferido.
- `kb` → tarea 09.
- Notificar tras un `reply` (FR-038) → hueco nombrado, plan 12.

## Scenarios (Gherkin)

Criterios de aceptación (Gherkin) en el caso de uso:
- [CU-BE-04 — Ciclo de vida del ticket](../../../specs/backend/casos-de-uso/CU-BE-04-ciclo-de-vida-del-ticket.md)

> Nota de alcance: de CU-BE-04 esta tarea cubre solo la parte de mensajes/adjuntos (el ciclo de vida del
> ticket en sí lo cubre la tarea 07).

```gherkin
Feature: mensajes de ticket con adjuntos en filesystem local

  Scenario: listar mensajes filtra los internal a quien no tiene el permiso
    Given un ticket con mensajes public e internal
    When un subject SIN note.internal.read hace GET /tickets/{id}/messages
    Then solo ve los mensajes public

  Scenario: listar mensajes muestra los internal a quien SÍ tiene el permiso
    Given un ticket con mensajes public e internal
    When un subject CON note.internal.read hace GET /tickets/{id}/messages
    Then ve ambos, ordenados por created_at ascendente

  Scenario: responder public requiere ticket.reply
    Given un subject sin ticket.reply
    When intenta POST /tickets/{id}/messages con visibility=public
    Then recibe 403

  Scenario: escribir una nota internal requiere note.internal.write
    Given un subject sin note.internal.write
    When intenta POST /tickets/{id}/messages con visibility=internal
    Then recibe 403

  Scenario: subir un adjunto lo persiste y lo hace recuperable
    Given un mensaje existente
    When se hace POST /messages/{id}/attachments con un fichero válido
    Then recibe 201 con el Attachment

  Scenario: descargar un adjunto ya subido devuelve su contenido
    Given un adjunto ya subido a un mensaje
    When se hace GET /messages/{id}/attachments/{attachment_id}
    Then recibe 200 con el contenido y content_type originales

  Scenario: dos adjuntos con el mismo filename al mismo mensaje no se sobrescriben
    Given un mensaje con un adjunto "informe.pdf" ya subido
    When se sube un segundo adjunto también llamado "informe.pdf" al mismo mensaje
    Then ambos quedan persistidos y son recuperables por separado (storage_key distinto)

  Scenario: un adjunto que excede el tamaño máximo se rechaza
    Given un fichero mayor que el límite configurado
    When se intenta subir como adjunto
    Then recibe 413, sin persistir nada

  Scenario: un adjunto exactamente en el límite se acepta
    Given un fichero de tamaño igual al máximo configurado
    When se intenta subir como adjunto
    Then se acepta (201)

  Scenario: un adjunto de 0 bytes se acepta o se rechaza (definir)
    Given un fichero vacío (0 bytes)
    When se intenta subir como adjunto
    Then el comportamiento es explícito (aceptado como adjunto vacío, o 422) — no un 500

  Scenario: subir un adjunto a un mensaje inexistente da 404
    Given un message_id que no corresponde a ningún Message
    When se hace POST /messages/{id}/attachments
    Then recibe 404

  Scenario: un fallo de Storage.save() se traduce a un error controlado
    Given un Storage cuyo save() falla (IO, disco lleno)
    When se sube un adjunto
    Then la respuesta es 502 problem+json (PortError), no un 500 crudo ni un 201 fantasma

  Scenario: responder con body vacío se rechaza
    Given un ticket existente
    When se hace POST /tickets/{id}/messages con body=""
    Then recibe 422

  Scenario: el hilo de mensajes de un ticket sin mensajes es una página vacía
    Given un ticket recién creado sin mensajes
    When se hace GET /tickets/{id}/messages
    Then recibe 200 con Page{items: [], total: 0}

  Scenario: el hilo de mensajes pagina igual que las demás listas
    Given un ticket con más mensajes que un page_size
    When se pide GET /tickets/{id}/messages con page/page_size
    Then devuelve la página correspondiente y el total correcto

  Scenario: la clave de storage no puede escapar el directorio raíz
    Given un intento de construir una key con ".." (path traversal)
    When LocalFilesystemStorage.save() se invoca con esa key
    Then se rechaza antes de tocar el filesystem
```

## Provides

`app.domain.ports.storage.Storage` (nuevo) + `LocalFilesystemStorage` en `app.infra.storage.local`;
`MessageRepository` en `app.infra.db.repositories.message`; router `messages` completo, incl. subida y
descarga de adjuntos.

## Definition of Done

- [x] Tests escritos ANTES de la implementación (Red → Green → Refactor).
- [x] Cada escenario tiene al menos un test de integración.
- [x] Todos los tests en verde (`make test`) — 587 tests, verde.
- [x] `Provides` disponible; el dominio no importa detalles de filesystem (solo el puerto).
- [x] `ruff check` (+`S`) + `ruff format --check` + `mypy` strict OK.
- [x] Gate de mutation `cosmic-ray` (`break: 80`) sobre el adaptador de storage (2.94%) y el router
  (7.69%).
- [x] Gate `/sdd-lint` (0 ERROR, 2 AVISO reconocidos — ausencia de FR de adjuntos en `spec.md`).
- [x] Gate de `fact-checker` (17/17 VERIFICADO).
- [x] Documentación: docstrings (por qué el puerto `Storage` no expone filesystem al router, la defensa
  anti path-traversal); session log con la traza a CU-BE-04 (`.claude/context/backend/backend-routers-core-08.md`).
