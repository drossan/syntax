# Session log — backend-domain-services-04

Tarea: `ticket_service` (máquina de estados, asignación, CSAT, auditoría) + puerto `SlaPolicy`.
Nivel: unit. Traza: CU-BE-04.

## Entradas

- 2026-08-18 — Arranque. Tarea 04 `active`. TDD escenario a escenario (RED primero).

## Resumen

`app/domain/ports/sla_policy.py`: `SlaPolicy.due_at(priority, from_, tenant_id) -> datetime | None`.
`app/domain/services/ticket_service.py`: `TicketService` con `create`/`transition`/`reopen`/`assign`/
`set_csat`, todos auditados vía `AuditLogRepository`. Máquina de estados como tabla de aristas exacta
(`frozenset` de pares válidos) — cualquier par no listado (incl. auto-transición) es `InvalidTransition`.

## Decisiones técnicas + porqué

- **Tabla de aristas como conjunto, no un grafo/diccionario de adyacencia**: 7 pares válidos caben en un
  `frozenset[tuple[TicketStatus, TicketStatus]]`; `(actual, destino) in _VALID_TRANSITIONS` es O(1) y
  hace la tabla auto-documentada (se lee entera de un vistazo).
- **`reopen()` reutiliza `transition()`** (no reimplementa la validación): llama a
  `self.transition(ticket_id, REOPENED)` y luego recalcula `sla_due` — evita duplicar la lógica de
  aristas/auditoría/`NotFound`.
- **`assign()` recibe `assignee_tenant_id` como parámetro** (no consulta `UserRepository`): el llamante
  (futuro router) ya resolvió el usuario y conoce su tenant; mantiene el servicio con menos puertos.
- **Prioridad por defecto `normal`** al crear (no está fijada en ninguna spec — asunción documentada aquí,
  ya que el clasificador, tarea 15, la corregirá después).

## Tests corridos + resultado

- TDD: 25 tests RED (ImportError) → GREEN (con un bug propio de desempaquetado de fixture corregido en el
  camino). Mutation gate reveló 3 supervivientes reales (comparación de tenant `!=` degenerada a
  `is not`/`>` por reusar el mismo objeto UUID) → reforzado con UUIDs deterministas + comparación por
  valor → **27 tests** finales.
- Suite completa `pytest -q` verde (**293 tests**, vía junitxml). `ruff check` OK · `ruff format --check`
  OK · `mypy app` strict Success (92 files).
- Mutation `cosmic-ray` sobre `ticket_service.py` (break 80): primera pasada **5.36%** (56 mutantes, 3
  supervivientes) → reforzado a **1.79%** (1 superviviente: `AddNot` en el ternario del payload de
  auditoría de `assign` — cosmético, no afecta estado observable, documentado como cuasi-equivalente).
- `/sdd-lint`: CU-BE-04 enlazado y bien formado → PASA.
- `fact-checker` (sonnet): **12/12 VERIFICADO, 0 INCORRECTO**. Re-ejecutó cosmic-ray y confirmó 1.79%
  exacto (56 jobs, 1 superviviente). Gate limpio.

## Docs actualizadas

- Docstrings de `ticket_service.py`/`sla_policy.py` (máquina de estados, por qué `reopened` no
  auto-encadena, hueco FR-030). Session log (este fichero) con la traza a CU-BE-04.
