# Session log — backend-domain-services-02

Tarea: `app/domain/errors.py` (jerarquía + taxonomía HTTP-derivable) + puertos base (repositorios,
clock, email). Nivel: unit. Rama: `plan/backend/domain-services`.

## Entradas

- 2026-08-18 — Arranque. Tarea 02 `active`. TDD escenario a escenario.

## Resumen

`app/domain/errors.py`: `DomainError` (base, `code`+`details`) + `NotFound`/`Conflict`/`InvalidTransition`
(hereda de `Conflict`)/`Validation`/`PortError` (alias `ExternalServiceError`). `app/domain/ports/
{clock,email,repositories}.py`: `Clock`, `EmailPort`, y 10 Protocols de repositorio
(`Tenant/User/Role/RefreshSession/AuthToken/Ticket/Message/Approval/AgentRun/Notification/AuditLog`).
`RefreshSessionRepository.rotate_if_active` y `ApprovalRepository.decide_if_pending` son **CAS**:
distinguen "no existe" (lanzan `NotFound`) de "existe pero no aplica" (`Reused`/`None`).

## Decisión de interpretación

`RotationOutcome = Rotated | Reused` es una **unión de 2**, no de 3 — el caso "hash no encontrado" se
señaliza **lanzando** `NotFound` (mismo patrón que `decide_if_pending`), no como un tercer miembro de la
unión. Evita la colisión de nombre entre un `NotFound` de datos (variante de retorno) y el `NotFound` de
`errors.py` (excepción) — un único símbolo, un único significado.

## Disciplina TDD (desviación reconocida)

Escribí `errors.py`/`ports/{clock,email,repositories}.py` **antes** que los tests: no hubo una pasada RED
real en esta tarea (los 23 tests pasaron a la primera ejecución). Desviación reconocida frente al RED→GREEN
estricto de las tareas 03-08 de `database-foundation` y la 01 de este plan.

## Tests corridos + resultado

- `tests/test_domain_errors_and_ports.py`: 23 tests — jerarquía de errores (herencia, `code`/`details`
  con default vacío), `PortError` + `__cause__`, fakes estructurales por puerto, CAS de
  `decide_if_pending` (NotFound vs None) y `rotate_if_active` (Rotated/Reused/NotFound).
- Suite completa `pytest -q` verde (**247 tests**, vía junitxml). `ruff check` OK (tras `--fix` de import
  wrapping) · `ruff format --check` OK · `mypy app` strict Success (91 files).
- Mutation `cosmic-ray` sobre `errors.py` (break 80): **survival 4.35%** (46 mutantes, 2 supervivientes
  `ReplaceBinaryOperator_Mul_Div`, causa no obvia en el código fuente — gate pasa con margen amplio).
- `/sdd-lint`: sin cambios de artefactos SDD (infra de contratos) → PASA.
- `fact-checker` (sonnet): **11/12 VERIFICADO, 1 INCORRECTO**. El único INCORRECTO fue un error mío en el
  *prompt* de verificación (dije "10 Protocols de repositorio"; el módulo define **11** — los mismos 11
  nombres que yo listé, simple desliz de conteo). No es un bug de código; no afecta a ningún fichero de
  plan/tarea persistido (ahí siempre se enumeraron por nombre, nunca por cifra). También re-ejecutó
  cosmic-ray y confirmó 4.35% (46 jobs, 2 supervivientes) exacto. Gate limpio.

## Docs actualizadas

- Docstrings de módulo/clase en `errors.py`, `ports/{clock,email,repositories}.py` (intención, CAS,
  anti-patrones). Session log (este fichero).
