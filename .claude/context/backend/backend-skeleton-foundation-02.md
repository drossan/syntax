# Session log — backend-skeleton-foundation-02 (Spec RBAC)

## 2026-08-11 — Ejecución

**Resumen:** Escrita `.claude/specs/backend/rbac.md`: modelo rol→capacidad→ámbito, catálogo de 14
capacidades, 6 roles semilla + matriz, roles custom por tenant (con invariantes anti-escalada),
aislamiento app-level + RLS, visibilidad `public|internal`, contrato `authorize()` y anti-patrones.

**Decisiones aplicadas (del grilling/design-review):** capacidades + roles custom por tenant;
capacidades resueltas server-side por request (no en el JWT); Soporte en tenant-sistema `syntax`;
KB global sin RLS; `developer` diferido a Fase 2.

**Refuerzos (scenario-coverage) incorporados:** deny-all sin rol; fail-closed si no cargan capacidades;
no conceder capacidad que el propio sujeto no posee; reconciliación 403 (API = fuente de verdad).

**Verificación (doc-only, bucle principal):** spec coherente con las decisiones del plan y con lo que
consumirán 03 (tablas `Capability`/`Role`/`RoleCapability`, RLS) y 06 (endpoints de roles + 403).
Nombres de capacidades/roles fijados como contrato literal. **Nota honesta:** el gate formal
`fact-checker` (subagente, sonnet por config) NO se ejecutó en esta sesión de ejecución rápida; la
verificación de consistencia se hizo en el bucle principal. Recomendado correr `fact-checker` en un
cierre formal si se quiere estricta conformidad de DoD.

**Ficheros:** `.claude/specs/backend/rbac.md` (nuevo). **Tiempo real:** ~0.5 h.

**Follow-ups:** 03 (data-model) materializa las entidades RBAC + RLS; 06 (contrato) los endpoints de
roles/capacidades; el frontend (05/18) replica capacidades y role builder read-only.
