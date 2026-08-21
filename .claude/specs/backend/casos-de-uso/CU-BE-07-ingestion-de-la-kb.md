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
- **1d.** `package`/`domain` del frontmatter no es uno de los valores válidos: el documento se **salta
  con log**, igual que un frontmatter malformado (1a) — no es un caso más grave.
- **3a.** El contenido de un chunk no cambió respecto a la ingesta anterior (mismo contenido para su
  `(uc_id, ordinal)`): no se re-embebe (ahorro).
- **3b.** Un UC editado tiene ahora menos secciones que en la ingesta anterior: los `kb_chunk`
  (y su `embedding`) cuyo `ordinal` ya no aparece en la nueva pasada se eliminan por reconciliación,
  aunque el documento siga vivo — no solo cuando el UC entero se retira.
- **1e.** Un `uc_id` duplicado (1b) bloquea TODO el run, altas y reconciliación por igual: si el batch
  falla, no se elimina ningún documento retirado en esa misma ejecución.
- **1f.** 3 o más ficheros declaran el mismo `uc_id`: el batch falla reportando **todos** los ficheros en
  conflicto para ese `uc_id`, no solo un par.
- **3c.** Un fallo real (no de validación) del proveedor de embeddings o de la escritura en BD a mitad de
  un batch con varios documentos: el run entero se aborta (mismo criterio "todo o nada" que 1b/1e,
  aplicado a cualquier causa de fallo, no solo a duplicados). Una re-ejecución posterior es segura por
  ser idempotente.
- **4a.** Ninguna ejecución concurrente: `ingest()` toma un advisory lock de Postgres al arrancar
  (`pg_try_advisory_lock`, no bloqueante); una segunda ejecución simultánea **falla claro de inmediato**
  (nunca espera, nunca corre en paralelo con la primera).
- **4b.** Un run sin documentos válidos que procesar (origen vacío o todo malformado): termina con éxito,
  reporta 0 procesados, y no toca la base de datos.

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

  Scenario: Chunk retirado de un documento que sigue vivo
    Given un UC ya ingerido cuya nueva versión tiene menos secciones que la anterior
    When se ingiere la KB
    Then los chunks y embeddings de las secciones retiradas se eliminan, y el documento sigue existiendo

  Scenario: uc_id duplicado bloquea también la reconciliación del mismo run
    Given un batch con un uc_id duplicado y, a la vez, un uc_id retirado del origen
    When se ingiere la KB
    Then el batch falla y el uc_id retirado NO se elimina en esa ejecución

  Scenario: Precedencia del package del frontmatter
    Given un UC cuyo package en el frontmatter difiere del de trazabilidad
    When se ingiere el documento
    Then prevalece el package del frontmatter y se registra la discrepancia

  Scenario: package o domain fuera de catálogo se salta
    Given un UC cuyo package o domain del frontmatter no es uno de los valores válidos
    When se ingiere la KB
    Then ese documento se salta con log y no entra en el corpus

  Scenario: 3 o más ficheros con el mismo uc_id reportan todos los conflictos
    Given tres documentos que declaran el mismo uc_id
    When se ingiere la KB
    Then el batch falla reportando los tres ficheros en conflicto, no solo un par

  Scenario: Un fallo real a mitad de un batch de varios documentos aborta todo el run
    Given un batch de varios documentos válidos donde el proveedor de embeddings o la escritura en BD
      fallan al procesar uno de ellos
    When se ingiere la KB
    Then el run entero se aborta, sin persistir ningún documento de esa ejecución

  Scenario: Ejecuciones concurrentes de la ingestión no se solapan
    Given una ejecución de la ingestión ya en curso
    When se intenta arrancar una segunda ejecución al mismo tiempo
    Then la segunda falla claro de inmediato, sin esperar, y nunca corre en paralelo con la primera

  Scenario: Un origen sin documentos válidos termina con éxito sin efecto
    Given un origen vacío o donde todos los documentos son malformados
    When se ingiere la KB
    Then el run termina con éxito, reporta 0 documentos procesados, y no se toca la base de datos
```
