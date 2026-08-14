# CU-BE-07 — Ingestión de la KB

> **SDD** (Cockburn + Gherkin). CÓMO para FR-032…FR-034 de [`../spec.md`](../spec.md). Decisión:
> [[../../adr/0010-rag-pgvector-chunking-h2-tolerante-estado-peso]]. Detalle: [`../rag-ingestion.md`](../rag-ingestion.md).

- **Ámbito**: backend (pipeline de ingestión CLI)
- **Nivel**: objetivo de usuario (operador)
- **Actor primario**: operador que ejecuta la ingestión (`make ingest`)
- **Interesados e intereses**:
  - Plataforma — KB fiel, sin duplicados, reproducible e idempotente.
  - Soporte — que el retrieval refleje la documentación real actual.

## Precondiciones

- La fuente `domains/*/uc/*.md` está disponible (268 UC / 17 dominios) con frontmatter y bloque Trazabilidad.

## Garantía mínima

- Un documento malformado no corrompe el corpus: se salta con log; un `uc_id` duplicado aborta el batch sin dejar estado a medias.

## Garantía de éxito (postcondición)

- Cada UC válido está como `kb_document` + `kb_chunk` + `embedding`; re-ingerir sin cambios no genera embeddings nuevos.

## Disparador

- Se ejecuta el pipeline de ingestión.

## Escenario principal (éxito)

1. El loader lee los `.md`; el parser extrae frontmatter (`title/domain/package/uc`) + Trazabilidad (`estado`).
2. El chunker parte por **H2 tolerante** (no asume estructura fija; no parte tablas/código; glosario del `index.md`).
3. El embedder genera vectores (`vector(N)`, N desde config) y el pipeline hace **upsert idempotente por `uc_id`**.
4. El pipeline reconcilia: los `uc_id` presentes en BD pero ausentes en origen se borran/tombstone.

## Extensiones (flujos alternativos y de error)

- **1a.** Frontmatter malformado o sin `uc_id`: el documento se **salta con log** (no entra).
- **1b.** `uc_id` **duplicado** entre ficheros: el batch **falla** reportando el par en conflicto.
- **1c.** `package` del frontmatter difiere del de Trazabilidad: **gana el frontmatter** y se loguea la discrepancia.
- **3a.** El contenido de un UC no cambió (mismo hash): no se re-embebe (ahorro).

## Reglas de negocio

- **RN-1** — La clave de upsert es `uc_id`; dos ficheros no pueden mapear al mismo `kb_document`.
- **RN-2** — El `source_url` se **deriva** de la ruta (el frontmatter no trae `url`).
- **RN-3** — Cambiar el modelo/dimensión de embeddings obliga a re-embeber todo el corpus (no en caliente).

## Criterios de aceptación (Gherkin)

```gherkin
Feature: Ingestión de la KB

  Scenario: Ingesta de un UC válido
    Given un documento de UC con frontmatter y bloque de trazabilidad válidos
    When se ingiere la KB
    Then el UC queda como documento con sus chunks y embeddings

  Scenario: Re-ingesta idempotente sin cambios
    Given una KB ya ingerida cuyos documentos no han cambiado
    When se vuelve a ejecutar la ingestión
    Then no se generan embeddings nuevos

  Scenario: Documento malformado se salta
    Given un documento con frontmatter no parseable o sin uc_id
    When se ingiere la KB
    Then ese documento se salta con log y no entra en el corpus

  Scenario: uc_id duplicado aborta el batch
    Given dos documentos que declaran el mismo uc_id
    When se ingiere la KB
    Then el batch falla y se reporta el par en conflicto

  Scenario: Documento retirado se reconcilia
    Given un uc_id presente en la base pero ausente en el origen
    When se ejecuta la ingestión
    Then su documento, chunks y embeddings se eliminan por reconciliación

  Scenario: Precedencia del package del frontmatter
    Given un UC cuyo package en el frontmatter difiere del de trazabilidad
    When se ingiere el documento
    Then prevalece el package del frontmatter y se registra la discrepancia
```
