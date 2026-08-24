# Fixtures — `source_type: packages-uc`

Raíz de fixtures del formato **real verificado** (`packages-uc`), separada de `tests/fixtures/kb/domains/`
(que es la del formato hipotético `vitepress-domains` y **no se toca**).

Reproducen la **estructura** real, no el vocabulario de marca de ninguna fuente concreta: los nombres de
subdirectorio de package son genéricos (`vendor-*`) y se traducen a valores de `Package` vía los alias de
deployment (tarea `-02`/`-03`).

Qué reproduce cada fichero del formato real:

| Fixture | Aspecto del formato real que reproduce |
|---|---|
| `packages/vendor-core/docs/aiup/use-cases/UC-CORE-001-*.md` | UC con frontmatter `id`/`dominio`/`estado`/`traza` (lista YAML de rutas), título como **primer H1 del cuerpo** (no hay `title` en el frontmatter) y secciones H2 narrativas. |
| `packages/vendor-core/docs/aiup/use-cases/UC-CORE-002-*.md` | Segundo UC del **mismo** package: la convención admite varios UC por subdirectorio; incluye wiki-links `[[UC-...]]` en el cuerpo (no se parsean — fuera de alcance del plan). |
| `packages/vendor-render/docs/aiup/use-cases/UC-RENDER-001-*.md` | UC en un **segundo** subdirectorio de package: el `package` se deriva de la ruta, no del frontmatter. |
| `packages/vendor-tooling/README.md` | Subdirectorio de package **sin** directorio de casos de uso (real: no todos los packages documentan UC) — ausencia que no es error. |
| `docs/aiup/glossaries/authoring-and-editor.md` | Glosario **plano por dominio** en la ubicación compartida: sin frontmatter y sin sección `## Glosario` (a diferencia de `vitepress-domains`) — se ingiere íntegro. |
| `docs/aiup/glossaries/platform-and-devex.md` | Segundo glosario: un fichero por dominio, nombre de fichero = dominio. |
| `legacy-site/domains/…/uc/UC-*.md` | **Árbol hermano con otra convención de carpeta** (una generación legacy de los mismos UC, real en la fuente verificada): nunca se recoge (extensión **1k** de `CU-BE-07`). |
