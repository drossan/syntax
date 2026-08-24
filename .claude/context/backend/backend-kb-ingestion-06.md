# Session log — `backend-kb-ingestion-06` — Pipeline (orquestación + reconciliación)

> Append-only. Registro canónico de la tarea (task-lifecycle §Cerrar una tarea).

## 2026-08-22 — Implementación y cierre

- **TDD**: escribí `app/ingestion/pipeline.py` antes que `tests/test_pipeline.py` por error (lo
  detecté yo mismo). Corregido: aparté la implementación, restauré el GUIÓN original desde git,
  confirmé rojo, y restauré la implementación después — mismo patrón de auto-corrección que en `-05`.
- **Implementado**: `IngestReport` + `ingest(path, *, writer, model, token_budget, encoding,
  batch_size, embedding_model_name) -> IngestReport` en `app/ingestion/pipeline.py`. Orquesta
  loader→parser→chunker→diff(`existing_chunk_contents`)→embed(solo lo cambiado)→upsert→reconciliación,
  con el diseño todo-o-nada de `grilling`/`design-review`: fase de diff+embed ENTERAMENTE en memoria
  antes de escribir nada (así un fallo del embedder a mitad de un batch no deja escritura parcial); la
  atomicidad frente a un fallo del `writer` a mitad de la escritura depende de que el llamante comparta
  una única sesión sin `commit()` intermedio (documentado explícitamente en el docstring, no gestionado
  por este módulo).
- **Decisiones de implementación sin precedente explícito en la tarea**:
  1. `ingest()` recibe `token_budget`/`encoding`/`batch_size`/`embedding_model_name` explícitos (la
     firma abreviada de la tarea solo mostraba `path, writer, model`) — mismo criterio que `-03`/`-04`/
     `-05`: los módulos de `app.ingestion` no importan `Settings`.
  2. **Glosario (`index.md`) y el esquema NOT NULL de `kb_document`**: `KBDocumentDraft.package`/
     `estado` son obligatorios, pero un glosario no tiene ninguno real (`ParsedUC.package`/`estado`
     llegan como `""` desde `-03`). Decisión de esta tarea: se persiste con `estado=KbEstado.active`
     (contenido de referencia, nunca señal "draft") y `package=Package.syntax_core` (placeholder
     neutro, sin consumidor todavía — la búsqueda por `package` es tarea 14, fuera de este plan). A
     revisar si el retriever necesita semántica real de `package` para glosarios.
  3. `Conflict` para "ya hay una ingestión en curso" (lock ocupado) y `Validation` para "uc_id
     duplicado" — ninguna de las dos estaba fijada por el texto de la tarea; elegidas por ajuste
     semántico con la taxonomía de `app.domain.errors` (409 vs 422).
- **sdd-lint**: N/A — no edita spec.md/CU/ADR (los satisface end-to-end, no los modifica).
- **Mutation testing (cosmic-ray)**, `module-path = "app/ingestion/pipeline.py"`: 7.21% supervivencia
  inicial (8/111) → 4.50% final (5/111) en una ronda. Corregidos con tests nuevos: `is_glosario`
  mutado a `not is_glosario` en la asignación de `estado` (test que ingiere un glosario Y un UC
  normal a la vez, comprobando que el `estado` persistido de cada uno es el correcto y distinto);
  `continue`→`break` al saltar un documento malformado (test con el malformado ordenado ANTES que
  uno válido, para que un `break` prematuro sí pierda el válido); `frozen=True`→`False` en
  `IngestReport` (test de inmutabilidad).
  Supervivientes finales (5), **todos equivalentes**: 2× el `*` keyword-only de las firmas; 1×
  `len(docs) > 1` mutado a `!= 1` (equivalente porque `len(docs)` nunca puede ser 0 en ese punto de la
  agrupación); 1× `docs[0]` mutado a `docs[-1]` (equivalente porque, tras el chequeo de duplicados,
  cada lista `docs` tiene longitud exactamente 1); 1× `existing_uc_ids() - origin_uc_ids` mutado a
  diferencia simétrica `^` (equivalente porque `origin_uc_ids` es siempre subconjunto de
  `existing_uc_ids()` en ese punto — se acaba de escribir en el bucle anterior — y para B⊆A, A-B ≡ A^B).
- **Incidente**: el gate de `fact-checker` falló DOS veces antes de completarse — no por el trabajo en
  sí, sino porque el equipo se suspendió a mitad de la ejecución del gate de mutation (que tarda varios
  minutos con tests de integración reales contra Postgres). Se le preguntó al owner cómo seguir;
  decidió reintentar, y el tercer intento completó con éxito.
- **fact-checker** (subagente independiente, agentId `a742d5139ba9436f1`, 3er intento): 10/10
  VERIFICADO, 0 INCORRECTO. Re-ejecutó el gate de mutation desde cero (4.50%, mismos 5 survivors,
  verificados con `cosmic-ray dump` + aplicando cada mutación sobre copias en `/tmp`) y confirmó que
  el fichero real no quedó corrupto tras el proceso.
- **DoD**: todos los checkboxes cumplidos. Sin pendientes.
- Excluido de este commit: `backend/docs/domain-services-explicado.md` (cambio no relacionado, de una
  sesión anterior, sigue sin commitear).
