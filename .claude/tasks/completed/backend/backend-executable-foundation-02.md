---
id: backend-executable-foundation-02
package: backend
plan: executable-foundation
status: done
priority: 1
depends_on: [backend-executable-foundation-01]
estimate: 1.5h
actual: ~1h
created: 2026-08-14
updated: 2026-08-15
---

# Scaffold de tests (make test verde) + ADR-0013 (arranque Fase 2)

## Description

Crea el **scaffold de tests** para que `make test` quede verde (habilita el TDD de 03–06) y registra en
un **ADR** la decisión —ya tomada— de arrancar la Fase 2 (código real). Tarea de **docs/scaffold**: el
único test es un *smoke* de arranque bajo el **carve-out** de `testing.md` §1 (no exige rojo previo).

## Spec

- `backend/tests/conftest.py`: base de fixtures (docstring); placeholder para settings inyectables que
  usarán 03+ (sin fixtures de DB — fuera de alcance).
- `backend/tests/test_smoke.py`: smoke test mínimo (p.ej. el paquete `app` importa; versión de Python
  esperada). Deja `make test` con **1 passed**.
- **ADR-0013** en `.claude/specs/adr/0013-arranque-fase-2-backend-codigo-real.md` (formato MADR, `status:
  accepted`): registra el arranque de Fase 2 y marca **0012 como superado**.
- Actualizar `.claude/specs/adr/adr-index.md`: añadir 0013; marcar 0012 `superseded-by 0013`.
- **Nota en ADR-0001**: `dev` nunca se adoptó; el flujo de facto es trunk-from-`main` (F8 de design-review).

## Fuera de alcance

- Código de producción (config/security/logging/factory → sus tareas).
- Fixtures de DB / integración (plan de capa DB).
- Reescribir 0012 (solo se marca superado, no se borra su histórico).

## Scenarios (Gherkin)

<!-- Tarea de SCAFFOLD/DOCS. El smoke test entra por el carve-out de testing.md §1 (scaffold de arranque,
     sin rojo previo). No hay comportamiento de dominio que modelar en Gherkin. SDD: crea ADR-0013 (MADR)
     + actualiza adr-index; el gate /sdd-lint valida ese ADR. Sin gate de mutation (el smoke no es código
     de negocio). -->

**Verificación**:
- `make test` → **1 passed** (smoke verde).
- ADR-0013 bien formado (MADR: contexto, decisión, consecuencias, status); `adr-index.md` coherente
  (0012 → superseded-by 0013). Lo valida `/sdd-lint`.

## Provides

`backend/tests/` + `conftest.py` (scaffold que 03–06 extienden con sus tests) y la capa SDD al día
(ADR-0013 + adr-index) para que los gates `/sdd-lint` de 03–06 encuentren la Fase 2 registrada.

## Definition of Done

- [x] `backend/tests/` + `conftest.py` + `test_smoke.py` → `make test` **verde** (1 passed).
- [x] ADR-0013 (MADR) escrito, supersede 0012; `adr-index.md` actualizado; nota en ADR-0001.
- [x] `make lint` + `make typecheck` OK.
- [x] Gate `/sdd-lint`: artefactos SDD (ADR MADR) sin ERROR — tras verificación, antes de `fact-checker`.
- [x] Gate de `fact-checker`: afirmaciones verificadas.
- [x] Documentación: docstrings en `conftest.py`; session log; ADR-0013 (doc técnica).

<!-- No aplican: TDD rojo-primero (smoke por carve-out), gate de mutation (sin código de producción). github-tracking off. -->
