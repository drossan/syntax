# Session log — backend-domain-services-05

Tarea: `notification_service` (emitir/listar/marcar-leída/contar-no-leídas), desacoplado.
Nivel: unit. Traza: CU-BE-10.

## Entradas

- 2026-08-18 — Arranque. Tarea 05 `active`. TDD escenario a escenario (RED primero).

## Resumen

`app/domain/services/notification_service.py`: `NotificationService` con `emit`/`list_for_user`/
`mark_read`/`count_unread`, todos delegando en `NotificationRepository`. Sin ningún otro servicio de
este plan como dependencia (desacoplado, decisión de grilling).

## Decisiones técnicas + porqué

- **`notification_type` en vez de `type`** como nombre de parámetro de `emit()`: `type` es builtin de
  Python; usar el nombre del campo de la entidad (`type=`) como kwarg al construir `Notification` está
  bien, pero como *parámetro* de la función se renombra para no ensombrecer el builtin.
- **`mark_read`/`count_unread` delegan la titularidad y el filtro al puerto**: el servicio no reimplementa
  "pertenece a este usuario" — confía en que `NotificationRepository.mark_read`/`count_unread` ya filtran
  por `user_id` (documentado en el contrato del puerto, tarea 02). Consistente con "app-level primero" del
  resto del plan.

## Tests corridos + resultado

- TDD: 8 tests RED (ImportError) → GREEN directo, sin sorpresas.
- Suite completa `pytest -q` verde (**301 tests**, vía junitxml). `ruff check` OK · `ruff format --check`
  OK · `mypy app` strict Success (92 files).
- Mutation: **N/A confirmado empíricamente** (cosmic-ray sobre `notification_service.py`: 0 jobs — el
  servicio es puro *pass-through*, sin `if`/comparaciones que mutar).
- `/sdd-lint`: CU-BE-10 enlazado y bien formado → PASA.
- `fact-checker` (sonnet): **8/8 VERIFICADO, 0 INCORRECTO**. Re-ejecutó cosmic-ray y confirmó "0 jobs".
  Gate limpio.

## Docs actualizadas

- Docstrings de `notification_service.py` (por qué desacoplado). Session log (este fichero) con la
  traza a CU-BE-10.
