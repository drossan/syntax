# Referencia · ADR (decisiones de arquitectura)

**Fuente canónica:** `.claude/specs/adr/` (MADR 4.0.0). Este sitio espeja el **índice**; el cuerpo de cada
ADR (contexto, opciones, consecuencias) vive en su fichero `NNNN-*.md`.

Las decisiones se **tomaron el 2026-08-11** (`grilling` + `design-review` de los planes) y se
**materializaron como ADR** el 2026-08-14 al activar la capa SDD (`features.sdd`). Todas están `accepted`.

| #    | Decisión                                                              | Estado   |
|------|----------------------------------------------------------------------|----------|
| 0001 | Monorepo pnpm + stack poligloto por-package + git flow dev→main       | accepted |
| 0002 | Contrato de API **OpenAPI-first** como única fuente de verdad         | accepted |
| 0003 | Frontend **SPA client-rendered** con access token en memoria          | accepted |
| 0004 | Auth **JWT** access(memoria) + refresh(cookie httpOnly) con rotación   | accepted |
| 0005 | **RBAC por capacidad + ámbito**; roles custom por tenant              | accepted |
| 0006 | Aislamiento multi-tenant **app-level + RLS** (KB global sin RLS)       | accepted |
| 0007 | **HITL asíncrono** sobre API con checkpointer **PostgresSaver**       | accepted |
| 0008 | Grafo LangGraph **plano con edges condicionales tipados**             | accepted |
| 0009 | **Confianza híbrida** → auto vs escalado; `auto_approve=false`        | accepted |
| 0010 | RAG: **pgvector** + dim. config + **chunking H2 tolerante** + peso `estado` | accepted |
| 0011 | Entrega del draft por **polling** (no streaming SSE en Fase 1)        | accepted |
| 0012 | Backend Fase 1 **doc-only**; **Fase 2 diferida**                     | accepted |

> Cómo se usa: cada spec/caso de uso enlaza a la ADR que justifica su diseño. Una decisión nueva entra como
> `0013-…` en `proposed`, y pasa a `accepted` cuando se cierra. El gate `/sdd-lint` valida el estado MADR.
