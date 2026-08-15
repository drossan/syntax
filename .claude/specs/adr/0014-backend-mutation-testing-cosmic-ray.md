# 0014. Backend: mutation testing con cosmic-ray (mutmut descartado)

- **Estado**: accepted
- **Fecha**: 2026-08-15
- **Decisores**: Owner.
- **Refina**: [[0013-arranque-fase-2-backend-codigo-real]] (que fijó `mutmut` como gate de mutation).

## Contexto y planteamiento del problema

La Fase 2 del backend exige un gate de mutation (`break: 80`) por tarea (0013); se eligió `mutmut`
(`task-pipeline.yml` `stack.packages.backend`). Al ejecutarlo por primera vez sobre `app/core/config.py`
(settings pydantic), `mutmut` 3.7.0 **no produjo score**: su mecanismo de *trampoline* no instrumenta
funciones **decoradas** (`@field_validator`/`@classmethod`, `@lru_cache`) ni las asignaciones a nivel de
clase (campos/defaults de pydantic-settings). Resultado: 0 mutantes útiles («could not find any test case
for any mutant»). Como casi todo módulo del backend usará pydantic + decoradores, `mutmut` deja el gate
ciego en la práctica.

## Decision drivers

- El gate debe **puntuar de verdad** el código real del backend (pydantic, decoradores, async).
- No contorsionar el código de producción para adaptarlo a las limitaciones de una herramienta.
- Mantener el gate rápido y **acotable** a los ficheros tocados por tarea.

## Opciones consideradas

- **Opción 1** — `cosmic-ray` (mutation testing AST-based): muta a nivel de módulo/clase/función, incluidas
  las decoradas; corre **in-place**; config en TOML; gate por `survival rate` (`cr-rate --fail-over`).
- **Opción 2** — Seguir con `mutmut` restringido a ficheros sin decoradores (deja la mayoría sin gate).
- **Opción 3** — Sin gate de mutation en el backend (`mutation-tool: none`): pierde la red de seguridad.

## Resultado de la decisión

Elegida: **Opción 1 (`cosmic-ray`)**. Verificado sobre `app/core/config.py`: 12 mutantes, 11 muertos, 1
superviviente **equivalente** (quitar `@classmethod` de un validator que no usa `cls`) → survival **8.33%**
(score **91.7% ≥ 80**). Integración: `stack.packages.backend.mutation-tool: cosmic-ray` +
`mutation-command: "make mutation"` (escape genérico del gate `/mutation`); config en
`backend/cosmic-ray.toml` (se **acota** `module-path`/`test-command` a los ficheros de cada tarea); target
`make mutation` (`cosmic-ray init` + `exec` + `cr-rate --fail-over 20`). `mutmut` se retira de
`requirements-dev.in` y de `pyproject.toml`.

### Confirmación

`.claude/task-pipeline.yml` (`stack.packages.backend`); `backend/Makefile` (target `mutation`);
`backend/cosmic-ray.toml`; tarea `backend-executable-foundation-03` cerrada con el gate en verde (2026-08-15).

## Consecuencias

- **Buenas**: gate de mutation **real** para código pydantic/decorado; in-place (sin el footgun de rutas
  de `mutmut`); acotable por tarea.
- **Malas / coste**: `cosmic-ray` es más pesado de configurar (TOML + sesión SQLite); el scope por tarea es
  **manual** (editar `module-path`/`test-command` en `cosmic-ray.toml`); los mutantes **equivalentes** se
  documentan a mano (no se excluyen del `survival rate` automáticamente).

## Pros y contras de las opciones

- **Opción 1**: 👍 puntúa pydantic/decoradores, in-place, acotable · 👎 setup más pesado, scope manual.
- **Opción 2**: 👍 no cambia de herramienta · 👎 deja sin gate la mayoría del backend.
- **Opción 3**: 👍 cero fricción · 👎 sin red de seguridad para auth/RLS/HITL.
