# Session log — backend-domain-services-03

Tarea: `rbac_service.authorize` (capacidad+ámbito, fail-closed, roles custom). Nivel: unit.
Traza: CU-BE-03.

## Entradas

- 2026-08-18 — Arranque. Tarea 03 `active`. TDD escenario a escenario (RED primero).

## Resumen

`app/domain/services/rbac_service.py`: `authorize(subject, capability, scope, resource) -> Allow | Deny`
(devuelve, no lanza — único servicio del plan con este contrato). `Deny(reason: DenyReason)` con
`no_capability` (403 futuro) / `out_of_scope` (404 futuro). `validate_role_composition(composer_caps,
requested_caps)` valida invariantes de rol custom (`rbac.md §4`): rechaza `scope="global"` y capacidades
que el componedor no posee.

## Decisiones técnicas + porqué

- **Lógica simple, sin "global implica tenant"**: `authorize` comprueba literalmente `(capability, scope)
  in subject.capabilities` — no asume que una capacidad concedida en `global` cubra automáticamente
  llamadas con `scope="tenant"`. El llamante (router futuro) pasa el `scope` que la operación necesita;
  `Subject.capabilities` ya trae el par exacto resuelto. Cubre los 6 escenarios de CU-BE-03 sin lógica
  adicional de "jerarquía de ámbitos".
- **KB global (RN-3)**: el chequeo de tenant solo se aplica si `scope == "tenant"` **y**
  `resource.tenant_id is not None` — un recurso global (KB) nunca entra en la comparación.

## Tests corridos + resultado (RED→GREEN real esta vez)

- TDD: 11 tests RED (ImportError) → GREEN inicial. Mutation gate reveló 8 supervivientes reales
  (comparaciones `==` de string/UUID degeneradas a `is`/`<`/`>`/`>=`/`<=`, y `frozen=True` de `Allow` sin
  probar) → añadidos 8 tests más (comparación de UUID por valor no identidad, ambos órdenes de mismatch,
  scope arbitrario que no dispara el chequeo de tenant, inmutabilidad de `Allow`) → **19 tests** finales.
- Suite completa `pytest -q` verde (**266 tests**, vía junitxml). `ruff check` OK · `ruff format --check`
  OK · `mypy app` strict Success (91 files).
- Mutation `cosmic-ray` sobre `rbac_service.py` (break 80): primera pasada **18.18%** (44 mutantes, 8
  supervivientes) → reforzado a **4.55%** (2 supervivientes). Los 2 restantes son `==`→`is` sobre
  literales de string cortos (`"tenant"`/`"global"`) — CPython interna esos strings, así que `is`/`==`
  son indistinguibles en la práctica (misma clase de mutante cuasi-equivalente que `RemoveDecorator` en
  tareas anteriores). Documentado, no perseguido más.
- `/sdd-lint`: CU-BE-03 enlazado y bien formado → PASA.
- `fact-checker` (sonnet): **9/9 VERIFICADO, 0 INCORRECTO**. Re-ejecutó cosmic-ray y confirmó 4.55%
  exacto (44 jobs, 2 supervivientes `Eq_Is`). Gate limpio.

## Docs actualizadas

- Docstrings de `rbac_service.py` (contrato, fail-closed, invariantes, discriminante). Session log (este
  fichero) con la traza a CU-BE-03.
