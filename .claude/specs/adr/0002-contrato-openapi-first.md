# 0002. Contrato de API OpenAPI-first como única fuente de verdad

- **Estado**: accepted
- **Fecha**: 2026-08-11
- **Decisores**: Owner; hallazgo **C1** de `design-review` (planes backend y frontend).

## Contexto y planteamiento del problema

Frontend y backend se encuentran en el **contrato de API**. Si el contrato se describe en **prosa**,
`contrato ↔ tipos ↔ mocks ↔ e2e` divergen **sin detección**: los tests del frontend validarían una
ficción y el backend implementaría otra cosa. ¿Cómo se fija el contrato para que el drift sea
**detectable mecánicamente**?

## Decision drivers

- Detección automática de divergencias contrato↔implementación↔mocks.
- Generación de tipos y mocks a partir de una fuente machine-readable.
- El backend puede materializar su superficie y verificar que la cubre.

## Opciones consideradas

- **Opción 1** — **OpenAPI 3.1 real** (`api-contract.yaml`) como única fuente; codegen de tipos + MSW
  validado contra el schema + **gate de conformidad** en CI.
- **Opción 2** — Contrato en **prosa** (`.md`) y tipos/mocks escritos a mano.
- **Opción 3** — Tipos TypeScript como fuente y documentación derivada informal.

## Resultado de la decisión

Elegida: **Opción 1 (OpenAPI-first)**. `.claude/specs/general/api-contract.yaml` (OpenAPI 3.1: 32 paths,
38 schemas) es la **única fuente de verdad**; el `.md` companion solo aporta convenciones. El **backend**
implementa contra el schema con el gate *"OpenAPI generado ⊇ contrato"* (el `/openapi.json` de FastAPI
debe cubrir el contrato). El **frontend** genera el cliente tipado (`openapi-typescript`) y **valida los
handlers MSW** (éxito y error) contra el `.yaml`, con su propio **gate de conformidad** en CI.

### Confirmación

`api-contract.yaml` (todos los `$ref` resuelven, verificado 2026-08-13); gate frontend `gen:api:check`
**sin drift** (helpdesk-core cerrado 2026-08-13); gate backend en tareas 11/12/19.

## Consecuencias

- **Buenas**: contrato ejecutable; drift detectado en CI; tipos y mocks fieles por construcción.
- **Malas / coste**: mantener el `.yaml` como artefacto de primera clase; **sin** validación formal contra
  el meta-schema OpenAPI todavía (`openapi-spec-validator` no instalado) → follow-up.

## Pros y contras de las opciones

- **Opción 1**: 👍 drift detectable, codegen fiable · 👎 coste de mantener el schema.
- **Opción 2**: 👍 fácil de escribir · 👎 divergencia silenciosa (el fallo que esto evita).
- **Opción 3**: 👍 un solo lenguaje · 👎 el backend Python no consume tipos TS; contrato acoplado al cliente.
