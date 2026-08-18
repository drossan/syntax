# Session log — backend-domain-services-01

Tarea: Entidades de dominio (identidad + negocio) + enums propios + test de drift dominio↔ORM.
Nivel: **unit** (sin Docker). Rama: `plan/backend/domain-services`.

## Entradas

- 2026-08-18 — Arranque. Plan movido a `active/`, tarea 01 `active`. Plan refinado con grilling +
  design-review + scenario-coverage. TDD escenario a escenario.

## Resumen

`app/domain/entities/{enums,identity,business}.py`: enums propios (13, mismo conjunto de valores que
`app.infra.db.models.enums`) + entidades Pydantic v2 (Tenant/User/Role/Capability/RefreshSession/
AuthToken/Subject en identity; Ticket/Message/ApprovalTask/AgentRun/Notification/Resource/AuditLogEntry
en business). `Subject` (conjunto efectivo de capacidades), `Resource` (tenant_id nullable para KB
global) y `AuditLogEntry` — las 3 entidades que `scenario-coverage`/design-review señalaron como
exigidas por los objetivos 4/5/9 sin estar nombradas en el guión original.

## Decisiones técnicas + porqué

- **Test de drift por AST**: en vez de comparar imports en runtime, `test_domain_does_not_import_infra`
  parsea el AST de cada módulo de `app.domain` y busca imports de `app.infra`/`sqlalchemy` — más robusto
  que un `grep` (detecta `import X as Y` y `from X import Y` por igual).
- **Enums independientes, no reexportados**: cada enum de dominio se define desde cero (mismos valores),
  no `from app.infra.db.models.enums import X as Y` — así el test de drift tiene sentido (si alguien
  cambia un valor en un solo lado, el test lo detecta; si se reexportara, nunca podría divergir).
- **`cosmic-ray` sobre `enums.py`: 0 jobs** (ningún operador mutable — asignaciones de string puras, sin
  comparaciones/condicionales). Confirma el N/A de mutation documentado en el DoD: el comportamiento real
  del drift vive en el test (AST + comparación de conjuntos), no en el código de producción que cosmic-ray
  muta.

## Tests corridos + resultado

- TDD: 18 tests RED (ModuleNotFoundError) → GREEN. `tests/test_domain_entities.py`: import hexagonal,
  13× drift de enum por valor, Subject, Resource (nullable), AuditLogEntry, rechazo Pydantic de enum
  inválido.
- Suite completa `pytest -q` verde (**224 tests**, vía junitxml). `ruff check` OK (tras `# noqa: S105` +
  combinar el `if` anidado en el propio test) · `ruff format --check` OK · `mypy app` strict Success (90
  files).
- Mutation: **N/A confirmado empíricamente** (cosmic-ray sobre `enums.py`: 0 jobs, sin operadores
  mutables).
- `/sdd-lint`: sin cambios de artefactos SDD (infra de tipos) → PASA.
- `fact-checker` (sonnet): **9/9 VERIFICADO, 0 INCORRECTO**. Re-ejecutó cosmic-ray y confirmó "0 jobs".
  Gate limpio.

## Docs actualizadas

- Docstrings de módulo/clase en `entities/{__init__,enums,identity,business}.py`. Session log (este
  fichero).
