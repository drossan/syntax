# Session log — backend-skeleton-foundation-04 (Spec RAG + ingestión de la KB)

## 2026-08-13 — Arranque

**Estado:** tarea movida `pending → active` (`status: active`, `updated: 2026-08-13`). `depends_on: []`.
Doc-only. Debe quedar coherente con 03 (tablas KB `kb_document`/`kb_chunk`/`embedding`) y con 05
(confianza híbrida; 05 aún no existe → aquí se fija el contrato de retrieval/confianza que 05 consumirá).

**Verificaciones previas a redactar (esta sesión, contra la KB real):**
- **5 packages** (frontmatter): `syntax-api`(125), `syntax-cx`(59), `syntax-core`(58), `syntax-ax`(19),
  `syntax-render`(7) = 268.
- **H2 reales** (confirman chunker TOLERANTE): `Comportamiento`(268) y `Fidelidad`(268) en todos;
  `Detalles observados en QA`(265), `Reglas e invariantes`(262), `Conceptos`(257) → **no** todos los UC
  traen las 5; además variantes (`Reglas e invariantes (draft — …)` ×5, H2 sueltos: `Matriz`, `Decisión`…).
- **estado**: **218 draft / 50 active** (la tarea decía "≈51"; valor real 50, ya confirmado por
  fact-checker en la 03 → corrijo el conteo).
- **index.md**: 17× `## Glosario` (per-domain) + 17× navegación (`Casos de uso`/`Todos los dominios`); el
  18º index.md es `domains/index.md` raíz (tabla de dominios, **sin** Glosario).
- **`Relacionado:`** presente en 258 UC → línea con links markdown a otros UC (grafo de relacionados).
- **Fallbacks existen**: `.vitepress/dist/llms.txt` (28.8K) y `.vitepress/dist/llms-full.txt` (1.4M).

## 2026-08-13 — Cierre

**Resumen:** Escrita `.claude/specs/backend/rag-ingestion.md`: fuente (268 UC/17 dominios/18 index +
fallback llms-full.txt), parsing (frontmatter `title/domain/package/uc` sin `url` → `source_url`
derivado; Trazabilidad `Estado`/`Traza`; `Relacionado:`), **chunking H2 tolerante** (H2 ausentes/
renombrados/sueltos, no partir tablas, glosario del index), categorización de 5 facetas con **peso de
`estado` explícito** (218 draft/50 active, 81% draft → no penalizar a ciegas), embeddings (puerto,
`text-embedding-3-small`, `vector(N)` desde config default 1536, upsert idempotente por `uc_id`), y el
**contrato de retrieval/confianza** (pgvector coseno + filtros domain/package/estado; confianza híbrida
similitud+grade; citas) que consumirá 05. Refuerzos cerrados: frontmatter malformado/`uc_id` dup→fail,
doc retirado→reconciliación (tombstone), precedencia `package` frontmatter-gana.

**Decisiones técnicas + porqué:**
- `estado` = señal de **re-ranking con peso config** (`RAG_ESTADO_WEIGHT`), NO filtro duro por defecto:
  el 81% del corpus es draft; filtrarlo vaciaría el retrieval. Filtrar por estado = opt-in por consulta.
- `uc_id` duplicado → **fail del batch** (colisiona la clave de upsert); ausente/malformado → skip+log.
- Doc retirado en origen → diff de `uc_id` presentes vs BD → borrado/tombstone en cascada (03 §7); no
  solo-upsert.
- Contrato de confianza partido: aquí la señal de **similitud** + forma de salida; 05 fija el **umbral**
  y la política auto/escalado/insuficiente→nota-al-humano (evita acoplar el retriever a la política).

**Verificación (gate `fact-checker`, subagente fresco, sonnet por config):** 10 afirmaciones → **9
VERIFICADO**, **1 INCORRECTO (B6)** = dos conteos de H2 (`Detalles observados en QA`, `Reglas e
invariantes`). Causa: yo conté **texto H2 exacto** (265/262); el verificador contó **agrupando variantes
a nivel de fichero** (266/268) — ambas métricas legítimas, la afirmación era ambigua. **Corregido**: §3
ahora da las cifras agrupadas /268 (268/257/268/266/268) como primarias + las exactas (262/265) con la
explicación de las variantes; recontado en sesión (`grep -lE '^## <sec>'` sobre `*/uc/*.md`) → coincide
con el conteo independiente del verificador. INCORRECTO resuelto.

**Docs actualizadas:** `.claude/specs/backend/rag-ingestion.md` (nuevo). Plan: `[x]` tarea 04 + Registro
de cambios (incl. corrección `estado` 51→50 y del método de conteo H2).

**Ficheros/commits:** `.claude/specs/backend/rag-ingestion.md` (nuevo); task 04 pending→active→completed;
session log; plan. (Commit pendiente de que el owner lo pida.)

**Tiempo real:** ~1 h.

**Follow-ups:** 13 implementa la ingestión (loader/parser/chunker H2 tolerante/embedder/CLI idempotente);
14 el retriever (pgvector + filtros + confianza + citas); 05 fija umbral de confianza + política auto/
escalado y consume la forma de salida del retriever. Nota: `Relacionado:` (grafo de relacionados) queda
como metadato opcional, expansión de contexto diferida a implementación.
