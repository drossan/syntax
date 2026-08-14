# 0001. Monorepo pnpm con stack poligloto por-package y git flow dev→main

- **Estado**: accepted
- **Fecha**: 2026-08-11
- **Decisores**: Owner (Daniel Rosselló); recomendado por `grilling` del pipeline (backend, rama 1).

## Contexto y planteamiento del problema

Syntax reúne tres piezas que comparten un **contrato de API** y un mismo método de trabajo: un
**frontend** Next.js/TypeScript, un **backend** Python/FastAPI y un **sitio de docs** VitePress. ¿Cómo
se organiza el repositorio, el gestor de paquetes y el flujo de ramas para que el contrato viva en un
único sitio, el tooling se comparta y cada package pueda tener su propio stack de tests?

## Decision drivers

- Contrato front↔back en un solo lugar, versionado junto al código que lo consume.
- Stack **poligloto** (TS con pnpm/Vitest/Stryker; Python con pytest/mutmut) sin forzar uno sobre el otro.
- El pipeline `task-pipeline` trabaja **por-package** (planes/tareas/specs bajo `<package>/`).
- Un flujo de ramas simple: trabajo en rama de plan → integración → release.

## Opciones consideradas

- **Opción 1** — Monorepo con **pnpm workspaces**, un package por área, stack override por-package.
- **Opción 2** — **Polyrepos** separados (uno por área) con el contrato duplicado o publicado como paquete.
- **Opción 3** — Monorepo **sin** workspaces (carpetas sueltas), tooling ad-hoc por carpeta.

## Resultado de la decisión

Elegida: **Opción 1 (monorepo pnpm workspaces)**, porque mantiene el contrato y el tooling compartidos
y encaja 1:1 con la unidad de trabajo del pipeline (`<package>`). El **stack por-package** se declara en
`.claude/task-pipeline.yml` (`stack.packages.backend` = Python/`test-runner: none` mientras es doc-only;
`frontend` hereda TS/pnpm/Vitest/Stryker). Git flow: rama `plan/<package>/<name-plan>` → `dev` (PR por
plan) → `main` (release), **nunca** feature directa sobre `main`.

### Confirmación

`pnpm-workspace.yaml` + `package.json` raíz; `.claude/task-pipeline.yml` con `stack.packages.backend`
(Python) activado el 2026-08-14; convención de ramas en `docs/guides/task-lifecycle.md`.

## Consecuencias

- **Buenas**: una fuente de verdad para el contrato; tooling y CI compartidos; PRs cohesionados por plan.
- **Malas / coste**: `pnpm` como raíz de un repo con un package Python que **no** lo usa (convención
  documentada: el backend usa pip-tools/Makefile); disciplina para no cruzar dependencias entre packages.

## Pros y contras de las opciones

- **Opción 1**: 👍 contrato/tooling compartidos, encaja con el pipeline · 👎 raíz pnpm sobre package Python.
- **Opción 2**: 👍 aislamiento total · 👎 contrato duplicado/publicado, drift y fricción cross-repo.
- **Opción 3**: 👍 cero config de workspaces · 👎 sin límites de package, tooling inconsistente.
