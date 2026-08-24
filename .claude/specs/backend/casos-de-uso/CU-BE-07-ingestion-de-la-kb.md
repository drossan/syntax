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

- La fuente de la KB está disponible y su **tipo** (`source_type`) está configurado. Dos tipos soportados:
  - **`packages-uc`** (default; formato **real verificado**): UC repartidos por subdirectorio de package
    (`packages/<pkg>/docs/aiup/use-cases/UC-*.md`, 268 UC / 17 dominios) + un glosario plano por dominio
    en una ubicación compartida. Frontmatter `id`/`dominio`/`estado`/`traza`; el título es el H1 y el
    `package` se deriva del subdirectorio traducido por los **alias configurados**.
  - **`vitepress-domains`** (formato hipotético, **nunca verificado** contra una fuente real):
    `domains/*/uc/*.md` con frontmatter `title`/`domain`/`package`/`uc` + bloque `::: info Trazabilidad`.

## Garantía mínima

- Un documento malformado no corrompe el corpus: se salta con log; un `uc_id` duplicado aborta el batch sin dejar estado a medias.

## Garantía de éxito (postcondición)

- Cada UC válido está como `kb_document` + `kb_chunk` + `embedding`; re-ingerir sin cambios no genera embeddings nuevos.

## Disparador

- Se ejecuta el pipeline de ingestión.

## Escenario principal (éxito)

1. El loader y el parser **del `source_type` configurado** leen los `.md` y extraen los metadatos
   (`uc_id`/`domain`/`package`/`estado`/`title`/`traza`), cada uno según la convención de su tipo.
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
- **1g.** El `source_type` pedido (por config o argumento de la CLI) no está registrado: la ejecución
  falla como **error de uso** (código de salida `2`, mensaje claro), sin tocar la base de datos y sin
  dejar escapar una traza cruda al operador.
- **1h.** *(`packages-uc`)* El subdirectorio de package de un UC **no tiene alias configurado**, o su
  alias apunta a un valor que **no es un `package` válido** del catálogo: el documento se **salta con
  log**, igual que un frontmatter malformado (1a) — un typo en la configuración no aborta el batch ni
  escapa como error inesperado.
- **1i.** *(`packages-uc`)* Un UC **sin encabezado H1**: se **salta con log** (no hay título del que
  derivar, y el frontmatter de este formato no trae `title`).
- **1j.** *(`packages-uc`)* `traza` viene como **string único** en vez de lista: se normaliza a una lista
  de un elemento; **no** es un documento malformado.
- **1k.** *(`packages-uc`)* El origen contiene un **árbol hermano con otra convención de carpeta** (p. ej.
  una generación legacy de los mismos UC): **nunca** se recoge — solo la convención que este tipo
  reconoce.
- **1l.** *(`packages-uc`)* **No hay ningún alias de package configurado** (el default): ningún UC supera
  1h, así que no se procesa nada. El run **avisa por stderr** de que la configuración de alias está
  vacía, para no confundirlo con un origen vacío legítimo (4b).
- **2a.** *(`packages-uc`)* El glosario de un dominio es un **fichero plano** sin frontmatter y sin
  sección `## Glosario`: se ingiere **íntegro** (a diferencia de `vitepress-domains`, donde solo el
  bloque `## Glosario` de un `index.md` se conserva).
- **1m.** La configuración de alias de package está presente pero **no es un JSON válido**: la ejecución
  falla como **error de uso** (código `2`), acotada a la ingestión. **Nunca** impide el arranque del resto
  de la aplicación (auth, tickets…): la config de alias se valida **de forma perezosa** donde se usa, no
  al construir `Settings` — mismo criterio y mismo motivo que el `source_type` (1g).
- **4c.** Se cambia el `source_type` entre ejecuciones **sobre la misma base de datos**: los documentos
  del formato anterior que no reaparecen en el nuevo origen se **reconcilian (se borran)**, porque la
  reconciliación compara `uc_id` origen-vs-BD **sin distinguir de qué tipo de fuente vino cada
  documento**. Es el comportamiento **esperado** (el origen es la fuente de verdad), no un defecto — pero
  es un efecto masivo que un operador puede disparar sin quererlo al cambiar la configuración, así que
  queda fijado por un test y advertido en la documentación.

## Reglas de negocio

- **RN-1** — La clave de upsert es `uc_id`; dos ficheros no pueden mapear al mismo `kb_document`.
- **RN-2** — El `source_url` se **deriva** de la ruta (el frontmatter no trae `url`).
- **RN-3** — Cambiar el modelo/dimensión de embeddings obliga a re-embeber todo el corpus (no en caliente).
- **RN-4** — El `source_type` determina **de dónde sale cada metadato**, no solo cómo se descubren los
  ficheros. La precedencia `package` frontmatter-vs-Trazabilidad (1c) es **específica de
  `vitepress-domains`**: en `packages-uc` el `package` tiene una única fuente (el subdirectorio + alias),
  así que no existe discrepancia posible que loguear.
- **RN-5** — La traducción subdirectorio→`package` de `packages-uc` es **configuración de deployment**
  (el vocabulario real de los packages del cliente), no una tabla en el código: sin configurarla, este
  tipo de fuente no ingiere nada (1l).

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

  # --- Selección del tipo de fuente y formato "packages-uc" (real verificado) ---

  Scenario: Un tipo de fuente no reconocido falla como error de uso
    Given una configuración que pide un tipo de fuente que no está registrado
    When se ejecuta la ingestión
    Then falla como error de uso, sin tocar la base de datos y sin exponer una traza cruda

  Scenario: Ingesta de un UC del formato real
    Given un UC del formato "packages-uc" con su identificador, dominio, estado y traza en el frontmatter
      And un alias configurado para el subdirectorio de package en el que vive
    When se ingiere la KB
    Then el documento queda ingerido con el título tomado de su encabezado principal
      And con el package resuelto a partir del alias configurado

  Scenario Outline: Normalización de la traza según cómo venga declarada
    Given un UC del formato real cuya traza se declara como <forma>
    When se ingiere la KB
    Then la traza del documento queda como <resultado>

    Examples:
      | forma                                | resultado                                   |
      | una lista de rutas                   | esa misma lista                             |
      | un valor suelto                      | una lista con ese único elemento            |
      | una lista vacía                      | una lista vacía                             |
      | ausente                              | una lista vacía                             |
      | una lista con elementos no textuales | una lista con su representación textual     |

  Scenario: Un package sin alias configurado se salta
    Given un UC que vive en un subdirectorio de package para el que no hay alias configurado
    When se ingiere la KB
    Then ese documento se salta con log y el resto del batch se procesa

  Scenario: Un alias que apunta a un package inexistente se salta
    Given un alias configurado cuyo valor no es un package del catálogo
    When se ingiere la KB
    Then el documento afectado se salta con log, sin abortar el batch ni fallar como error inesperado

  Scenario: Un UC sin encabezado principal se salta
    Given un UC del formato real que no tiene encabezado principal del que derivar su título
    When se ingiere la KB
    Then ese documento se salta con log y no entra en el corpus

  Scenario: Sin ningún alias configurado no se ingiere nada y se avisa
    Given una configuración sin ningún alias de package
    When se ingiere la KB del formato real
    Then no se procesa ningún documento
      And se avisa de que la configuración de alias está vacía, distinguiéndolo de un origen vacío

  Scenario: El glosario del formato real se ingiere íntegro
    Given un glosario de dominio que es un fichero plano, sin frontmatter ni sección de glosario
    When se ingiere la KB
    Then su contenido completo queda ingerido como el glosario de ese dominio

  Scenario: Un árbol hermano con otra convención de carpeta nunca se recoge
    Given un origen que contiene, junto a la convención reconocida, un árbol hermano con otra convención
    When se ingiere la KB
    Then ningún documento del árbol hermano entra en el corpus

  # --- Configuración del tipo de fuente y transición entre formatos ---

  Scenario: Una configuración de alias con JSON inválido falla acotada a la ingestión
    Given una configuración de alias de package cuyo contenido no es un JSON válido
    When se ejecuta la ingestión
    Then falla como error de uso con un mensaje claro
      And el arranque del resto de la aplicación no se ve afectado

  Scenario: Un tipo de fuente que no usa alias no dispara el aviso de alias vacío
    Given un tipo de fuente que no requiere alias de package
      And una configuración sin ningún alias
    When se ingiere la KB
    Then no se avisa de alias vacíos

  Scenario Outline: El tipo de fuente solo se reconoce en su forma canónica
    Given una invocación que pide el tipo de fuente en <forma>
    When se ejecuta la ingestión
    Then <resultado>

    Examples:
      | forma                       | resultado                             |
      | su forma canónica exacta    | se usa ese tipo de fuente             |
      | la misma con otra caja      | falla como error de uso               |
      | un nombre que no existe     | falla como error de uso               |

  Scenario: Cambiar el tipo de fuente entre ejecuciones reconcilia el formato anterior
    Given una KB ya ingerida con un tipo de fuente
    When se vuelve a ingerir con otro tipo de fuente sobre la misma base de datos
    Then los documentos del formato anterior que no reaparecen en el nuevo origen se reconcilian

  # --- Descubrimiento de ficheros (formato real) ---

  Scenario: El orden de descubrimiento sigue la convención documentada
    Given un origen con UC en varios subdirectorios de package y varios glosarios
    When se descubren los documentos de la KB
    Then los UC aparecen antes que los glosarios
      And dentro de cada grupo el orden es alfabético y estable entre ejecuciones

  Scenario Outline: Entradas que matchean el patrón pero no son documentos ingeribles
    Given un origen que contiene <entrada>
    When se descubren los documentos de la KB
    Then esa entrada se ignora sin error y el resto del recorrido se completa

    Examples:
      | entrada                                                             |
      | un directorio cuyo nombre matchea el patrón de UC                   |
      | un fichero del directorio de casos de uso sin el prefijo de UC      |
      | un UC anidado más profundo que el nivel de la convención            |
      | un glosario dentro de un package, no en la ruta compartida          |
      | un fichero de UC cuyo prefijo o extensión difieren en la caja       |

  Scenario Outline: Ausencias en el árbol de origen no rompen el recorrido
    Given un origen sin <ausencia>
    When se descubren los documentos de la KB
    Then el recorrido se completa y devuelve el resto de documentos

    Examples:
      | ausencia                                     |
      | el directorio de casos de uso de un package  |
      | el directorio compartido de glosarios        |

  Scenario: Un directorio sin permisos de lectura se salta con log
    Given un directorio del origen sin permisos de lectura
    When se descubren los documentos de la KB
    Then ese directorio se salta con log y el resto del recorrido se completa

  # --- Parseo (formato real): título y metadatos ---

  Scenario: Una línea de comentario dentro de un bloque de código no se confunde con el título
    Given un UC cuyo cuerpo tiene un bloque de código con una línea que empieza por almohadilla
      And un encabezado principal real en el documento
    When se parsea
    Then el título es el del encabezado real, no el de la línea del bloque de código

  Scenario: Con varios encabezados principales se toma el primero
    Given un UC cuyo cuerpo tiene más de un encabezado principal
    When se parsea
    Then el título es el del primero

  Scenario: Una ruta que no sigue la convención de package se salta como malformado
    Given un documento cuya ruta no contiene el segmento de package
    When se parsea
    Then se salta como malformado, sin lanzar una excepción no controlada

  Scenario: Un identificador de tipo no textual se salta como malformado
    Given un UC cuyo identificador en el frontmatter no es un valor textual
    When se parsea
    Then se salta como malformado

  Scenario: Un glosario vacío se ingiere como glosario sin contenido
    Given un fichero de glosario sin contenido
    When se parsea
    Then queda como el glosario de su dominio con cuerpo vacío, no como malformado
```
