# docs/ — Documentación del proyecto (VitePress)

Sitio de documentación de **Syntax**, construido con [VitePress](https://vitepress.dev).

## Arrancar

```bash
pnpm install                                   # desde la raíz del monorepo (instala vitepress)
pnpm --filter @syntax/docs docs:dev     # servidor de desarrollo
pnpm --filter @syntax/docs docs:build   # build estático → docs/.vitepress/dist
pnpm --filter @syntax/docs docs:preview # previsualiza el build
```

> Aún no se ha ejecutado `pnpm install`; el scaffold (config + páginas) está listo para arrancar.

## Estructura

```
docs/
  .vitepress/config.mts     # nav + sidebar + tema
  index.md                  # home (hero)
  getting-started.md
  architecture.md
  backend/                  # visión general, specs, guía de implementación
  frontend/                 # visión general
  reference/                # api-contract, data-model, rbac, rag, agent-graph, glosario
  guides/task-lifecycle.md  # método de trabajo (task-pipeline)
```

## Principio: no duplicar la fuente de verdad

Las decisiones canónicas viven en las **specs** (`.claude/specs/`) y en los guiones por fichero del
código. Este sitio es una **síntesis navegable** que resume y **enlaza** a esas fuentes; no las copia (para
evitar drift). Ante cualquier discrepancia, mandan la spec / el guión del código.
