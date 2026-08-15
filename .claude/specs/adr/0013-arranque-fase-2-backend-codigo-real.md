# 0013. Arranque de Fase 2 del backend (código real, TDD)

- **Estado**: accepted
- **Fecha**: 2026-08-14
- **Decisores**: Owner (el backend es también su ejercicio para pasar de Python básico a avanzado).
- **Supersede (parcial)**: [[0012-backend-fase-1-doc-only-fase-2-diferida]] — la parte «Fase 2 diferida».

## Contexto y planteamiento del problema

El plan `skeleton-foundation` cerró la **Fase 1 doc-only** ([[0012-backend-fase-1-doc-only-fase-2-diferida]]):
esqueleto hexagonal, guión por fichero, specs coherentes y contrato OpenAPI. 0012 dejó la implementación real
**diferida**. Con el contrato estable y el esqueleto navegable, toca **arrancar la Fase 2**: construir el
código de negocio a mano, con TDD, sin romper los contratos que ya consume el frontend (vía mocks MSW).
¿Se arranca ya, y con qué disciplina (TDD, gates)?

## Decision drivers

- El esqueleto + specs + contrato de Fase 1 ya fijan el «qué»; falta el «cómo» ejecutable.
- El backend es el vehículo de aprendizaje del owner (Python básico → avanzado): el owner escribe el código.
- No regresar en calidad: el resto del repo corre TDD + mutation; el backend debe igualarlo al pasar a código real.
- Acotar el arranque a **cimientos** (entorno + primitivas sin estado) antes de las capas con DB/IA.

## Opciones consideradas

- **Opción 1** — Arrancar Fase 2 **con TDD + gates** (pytest + `mutmut` break:80 + `sdd-lint` + `fact-checker`),
  empezando por el plan `executable-foundation` (entorno ejecutable + config/seguridad/logging/app factory).
- **Opción 2** — Implementar el backend sin TDD (código primero, tests después / opcionales).
- **Opción 3** — Seguir difiriendo y ampliar el esqueleto doc-only.

## Resultado de la decisión

Elegida: **Opción 1**. Se activa `stack.packages.backend` (`test-runner: pytest`, `mutation-tool: mutmut`,
`break: 80`) en `task-pipeline.yml` (2026-08-14) y el HOW-TO del backend pasa a exigir TDD. El primer plan de
Fase 2 es `executable-foundation` (cimientos ejecutables). 0012 queda **superado en su parte «Fase 2
diferida»**; su decisión de hacer Fase 1 doc-only primero se mantiene válida y ejecutada. Los huecos que 0012
y `spec.md` declararon (SSO/OIDC, GDPR/retención, streaming SSE [[0011-entrega-draft-por-polling-no-sse-fase-1]])
**siguen diferidos** a sus planes.

### Confirmación

`task-pipeline.yml` `stack.packages.backend` (pytest/mutmut); `.claude/specs/backend/HOW-TO-START-A-TASK.md`
(gate TDD imperativo); plan `.claude/plans/active/backend/executable-foundation.md` (grilling + design-review
+ scenario-coverage); tarea `backend-executable-foundation-01` cerrada con `fact-checker` 7/7 (2026-08-15).

## Consecuencias

- **Buenas**: el backend empieza a **ejecutar** con red de seguridad (TDD + mutation); el owner aprende
  implementando; calidad homogénea con el resto del repo.
- **Malas / coste**: TDD + gates añaden ceremonia por tarea; el gate `mutmut` es un camino que el plugin marca
  como «no verificado» y hubo que sanear (versión 3.7.0, clave `source_paths`).

## Pros y contras de las opciones

- **Opción 1**: 👍 backend ejecutable + calidad homogénea + valor pedagógico · 👎 más ceremonia por tarea.
- **Opción 2**: 👍 avance rápido inicial · 👎 sin red de seguridad; regresión de calidad frente al frontend.
- **Opción 3**: 👍 cero riesgo de implementación · 👎 el backend nunca ejecuta; el contrato no se valida.
