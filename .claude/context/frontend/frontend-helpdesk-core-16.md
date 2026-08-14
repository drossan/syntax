# Session log — frontend-helpdesk-core-16 (Base de conocimiento)

## 2026-08-13 — arranque
- Gate TDD: `status: active`; depends_on [06, backend-06] en `done`; rama del plan. Baseline 206 tests.

### Gap de contrato (alcance)
- `KBDocument` = {uc_id, domain, package, estado, title, source_url, updated} — **sin secciones ni grafo de relacionados**. → La vista de documento muestra la metadata + enlace a `source_url`; las "secciones" ricas quedan pendientes de un schema más completo. **Relacionados**: se derivan por **mismo dominio** (`GET /kb/documents?domain=X`, excluyendo el propio uc_id) como heurística honesta con el contrato.
- Búsqueda: `GET /kb/search?q=…` (q obligatoria) → `KBSearchHit` con title/domain/estado/snippet/score — totalmente soportada.

### Decisiones de diseño
- Lógica pura `.ts` (mutación): `kb-query.ts` → `buildKbSearchQuery(input)` (q + filtros no vacíos, page clamp), `kbSearchQueryKey`, `relatedDocuments(docs, excludeUcId)`.
- Hooks `.ts`: `use-kb.ts` → `useKbSearch(params)` (enabled con q no vacía), `useKbDocument(ucId)`, `useKbRelated(domain, excludeUcId)`.
- Presentación `.tsx`: `kb-search.tsx` (input + filtros + resultados + estados), `kb-document.tsx` (metadata + source + relacionados). Páginas `app/(app)/kb/page.tsx` y `app/(app)/kb/[uc_id]/page.tsx` guard `kb.read`.

## 2026-08-13 — cierre
- **Nuevos**: `src/features/kb/{kb-query.ts, use-kb.ts, kb-search.tsx, kb-document.tsx}` + tests; páginas `app/(app)/kb/{page.tsx,[uc_id]/page.tsx}`; fixtures `kbSearchHitFixture`/`kbDocumentFixture`. **Modificados**: `messages/{es,en}.json` (namespace `kb`).
- **Tests (salida real)**: `pnpm test` → **226 passed / 49 files**; typecheck limpio; lint `No issues found`.
- **Mutación**: Stryker sobre `kb-query.ts` + `use-kb.ts` → **90.74% ≥ 80** (query 95.45%, hooks 87.50%). Requirió extraer builders de queryKey puros (`kbSearchKey`/`kbDocumentKey`/`kbRelatedKey`) y contadores de llamada en los tests de "no fetch" para matar los mutantes de `enabled`.
- **Fact-checker** (sonnet): **10/10 VERIFICADO** (confirma gap: KBDocument sin secciones/relacionados).
- **Qué falta**: "secciones" del documento y grafo real de relacionados esperan un schema KB más completo; hoy relacionados = mismo dominio (heurística). **Tiempo real**: ~1.3h.
