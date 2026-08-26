# CU-BE-12 — Consulta de la KB desde el panel

> **SDD** (Cockburn + Gherkin). CÓMO para FR-049…FR-056 de [`../spec.md`](../spec.md). Decisiones:
> [[../../adr/0010-rag-pgvector-chunking-h2-tolerante-estado-peso]],
> [[../../adr/0018-retrieval-http-de-la-kb-ventana-dedup-y-peso-de-estado]]. Detalle:
> [`../rag-ingestion.md`](../rag-ingestion.md) §4 y §6, [`../../general/api-contract.md`](../../general/api-contract.md).
>
> **Distinto de [CU-BE-05](./CU-BE-05-clasificacion-y-retrieval-rag.md)**, que cubre el retrieval del
> **agente LangGraph** (chunks con `chunk_id`, sin deduplicar, dentro de un `agent_run`). Aquí el actor
> es una **persona** navegando la KB, y la unidad de resultado es el **documento**, no el chunk. Los dos
> comparten la capa de recuperación (`app/rag/`) pero no su forma de salida.

- **Ámbito**: backend (router `kb` + adaptador de lectura sobre pgvector)
- **Nivel**: objetivo de usuario
- **Actor primario**: usuario del panel con la capacidad `kb.read`
- **Interesados e intereses**:
  - Soporte — encontrar el UC que resuelve el ticket que tiene delante, sin leerse 268 documentos.
  - Plataforma — que un despliegue mal configurado se distinga de "no hay resultados".

## Precondiciones

- La KB está ingerida en pgvector ([CU-BE-07](./CU-BE-07-ingestion-de-la-kb.md)).
- El sujeto tiene `kb.read` (ámbito `tenant` o `global`; la KB es un recurso **global** sin RLS,
  [CU-BE-03](./CU-BE-03-autorizacion-y-aislamiento-tenant.md) RN-3).

## Garantía mínima

- Un fallo del proveedor de embeddings, un fallo de la base de datos o una petición mal formada
  **nunca** se presentan como "la KB no tiene resultados": se distinguen con su propio código de error.

## Garantía de éxito (postcondición)

- El usuario obtiene una página de documentos ordenada por relevancia, cada uno con el fragmento de la
  sección que lo justifica, y puede abrir cualquiera por su `uc_id`.

## Disparador

- El usuario busca un término en `/kb`, navega el listado, o abre un documento por su `uc_id`.

## Escenario principal (éxito)

1. El usuario introduce un término de búsqueda.
2. El sistema **embebe la consulta** y recupera por similitud coseno una **ventana de documentos**
   (su tamaño y cómo se sirve son detalle de [ADR-0018](../../adr/0018-retrieval-http-de-la-kb-ventana-dedup-y-peso-de-estado.md)).
3. El sistema aplica el **peso de `estado`** (re-ranking, no filtro) y **deduplica por `uc_id`**,
   quedándose con el mejor chunk de cada documento.
4. El sistema devuelve la página pedida, ordenada por `score` descendente, con `uc_id`, título, tipo de
   sección, `snippet` y `score`.

## Extensiones (flujos alternativos y de error)

- **1a.** El término está vacío, es solo espacios, o **excede la longitud máxima**: se rechaza como
  **petición mal formada (422)** sin llegar a llamar al proveedor de embeddings.
- **2a.** El proveedor de embeddings falla (caído, sin clave, timeout): **502**, distinguible de un
  resultado vacío.
- **2b.** El proveedor responde con un vector de **dimensión distinta** a la configurada: se trata como
  fallo del puerto (**502**), no se deja llegar a la comparación pgvector — donde reventaría como error
  de driver, sin decir qué pasó realmente.
- **2c.** El corpus contiene vectores de **más de un modelo** de embeddings: solo participan los del
  modelo configurado — comparar vectores de espacios distintos daría un orden verosímil pero falso.
- **2d.** Un chunk **sin embedding** (ingesta parcial) no participa del resultado y no rompe la consulta.
- **2e.** Falla la **base de datos** (no el proveedor): **502**, también en `/kb/documents`, que no
  necesita embeddings para nada.
- **3a.** La mayoría del corpus está en `draft` (81% real): los `draft` **participan ponderados**, nunca
  excluidos — penalizarlos a ciegas vaciaría el retrieval.
- **3b.** El usuario pide explícitamente un `estado`: entonces sí actúa como **filtro duro** — es el
  comportamiento **opt-in** de RN-2, distinto del re-ranking.
- **4a.** Ningún documento casa con la consulta o con sus filtros: página **vacía con `total: 0` y sin
  error** — resultado legítimo, no fallo.
- **4b.** La página solicitada cae **más allá de la ventana** de recuperación: se devuelve una página
  vacía, conservando el `total` de la ventana.
- **5a.** Se pide un documento cuyo `uc_id` no existe —incluido un `uc_id` con forma inesperada—:
  **404**, sin revelar nada más.

## Reglas de negocio

- **RN-1** — La unidad de resultado de `/kb/search` es el **documento**, no el chunk: un `uc_id` aparece
  **una sola vez** por búsqueda, representado por su chunk de mayor `score`.
- **RN-2** — `estado` es una señal de **re-ranking con peso** por defecto, y **filtro duro solo cuando el
  usuario lo pide explícitamente**. Nunca filtra por su cuenta
  ([ADR-0010](../../adr/0010-rag-pgvector-chunking-h2-tolerante-estado-peso.md)).
- **RN-3** — El `total` de `/kb/search` cuenta **documentos distintos dentro de la ventana de
  recuperación**, no el corpus entero: una búsqueda ANN no tiene cardinalidad. Se documenta como tal.
- **RN-4** — El `score` que devuelve `/kb/search` es la **relevancia re-rankeada**, no una similitud
  coseno cruda: incorpora el peso de `estado` y por tanto puede superar `1.0`. La similitud cruda se
  acota a `[0, 1]` antes de ponderarse — una similitud negativa es "menos relacionado que el azar" y no
  aporta ranking que preservar.
- **RN-5** — El `snippet` es el **principio de la sección ganadora**, truncado por límite de palabra —
  **no** un extracto centrado en el término buscado: la búsqueda es semántica y un chunk puede casar sin
  contener la palabra.
- **RN-6** — El listado de documentos tiene **orden determinista** (`uc_id` ascendente): la paginación
  debe ser estable ([`api-contract.md`](../../general/api-contract.md)).
- **RN-7** — La KB es **global**: ningún resultado se filtra ni se acota por `tenant_id`. Sin escenario
  propio **a propósito**: la autorización (`kb.read` presente/ausente → 403) y el aislamiento tenant los
  fija [CU-BE-03](./CU-BE-03-autorizacion-y-aislamiento-tenant.md), y este camino reutiliza
  `require_capability` **sin cambios** — descarte explícito de `scenario-coverage`, no un hueco.
- **RN-8** — La estabilidad de la paginación se garantiza **dentro de una ventana de recuperación**, no
  entre peticiones separadas en el tiempo: una re-ingestión concurrente puede alterar los resultados de
  páginas sucesivas. **Limitación aceptada** (problema general de cualquier ANN paginado, no específico
  de esta capacidad); registrada en ADR-0018 en vez de resolverse con cursores.
- **RN-9** — Los **glosarios** son documentos de pleno derecho del camino de lectura: se listan, se
  buscan y se abren por su `uc_id` sintético (prefijo `__glosario__:`, `app/ingestion/parser.py`).
  ⚠️ **Sesgo conocido**: la ingestión les asigna `package`/`estado` **por defecto** (`syntax-core` /
  `active`, `app/ingestion/pipeline.py`) porque su formato no los trae. Filtrar por esos valores
  arrastra glosarios que no pertenecen ahí de verdad. Es un defecto **de la ingestión**, no de la
  lectura: se documenta aquí y se corrige donde nace (fuera de alcance de este CU).

## Criterios de aceptación (Gherkin)

```gherkin
Feature: Consulta de la KB desde el panel

  # ─────────────── Búsqueda: camino feliz y relevancia ───────────────

  Scenario: La búsqueda devuelve documentos ordenados por relevancia
    Given una KB ingerida con documentos de relevancia distinta para un término
    When un usuario con kb.read busca ese término
    Then obtiene los documentos ordenados por score descendente
    And cada resultado indica su uc_id, su título y el tipo de sección que casó

  Scenario: Un documento con varias secciones relevantes aparece una sola vez
    Given un documento cuyas secciones casan todas con el término buscado
    When un usuario busca ese término
    Then el documento aparece una única vez en los resultados
    And lo representa su sección de mayor score

  Scenario: El resultado incluye un fragmento de la sección que lo justifica
    Given un documento cuya sección relevante es más larga que el límite del fragmento
    When un usuario lo obtiene como resultado de una búsqueda
    Then el fragmento muestra el principio de esa sección
    And está cortado en un límite de palabra, no a mitad de una

  Scenario: Una similitud negativa no invierte el orden de los resultados
    Given un documento active cuya similitud con la consulta es negativa
    And un documento draft de similitud cero
    When un usuario realiza la búsqueda
    Then la relevancia del documento active no queda por debajo de la del draft

  # ─────────────── Búsqueda: estado, filtros y vacío legítimo ───────────────

  Scenario: Los borradores participan ponderados, no excluidos
    Given una KB donde la mayoría de documentos está en estado draft
    When un usuario busca un término que casa con documentos draft y active
    Then los draft aparecen en los resultados
    And un active no adelanta a un draft claramente más relevante

  Scenario: Sin desempate configurado el orden es el de la similitud pura
    Given un peso de estado configurado a cero
    When un usuario busca un término que casa con documentos draft y active
    Then los resultados quedan ordenados solo por su similitud

  Scenario: Pedir un estado concreto sí lo filtra
    Given una KB con documentos draft y active que casan con el término
    When un usuario busca restringiendo el estado a active
    Then ningún resultado está en estado draft

  Scenario: Los filtros acotan la búsqueda
    Given una KB con documentos de varios dominios y packages
    When un usuario busca restringiendo el dominio
    Then todos los resultados pertenecen a ese dominio

  Scenario: Los filtros combinados acotan por conjunción
    Given una KB con documentos que combinan varios dominios, packages y estados
    When un usuario busca restringiendo dominio, package y estado a la vez
    Then todos los resultados cumplen las tres restricciones

  Scenario: Una búsqueda sin coincidencias devuelve vacío, no un error
    Given una KB cuyos documentos no casan con los filtros pedidos
    When un usuario realiza la búsqueda
    Then obtiene una página vacía con total cero
    And no obtiene ningún error

  Scenario: Pedir más resultados de los que existen devuelve solo los que hay
    Given una KB con menos documentos relevantes que el tamaño de página pedido
    When un usuario realiza la búsqueda
    Then obtiene todos los documentos relevantes que existen
    And el resultado no se rellena con documentos irrelevantes

  # ─────────────── Búsqueda: entrada inválida ───────────────

  Scenario Outline: Un término de búsqueda inutilizable se rechaza sin consultar al proveedor
    Given un usuario con kb.read
    When busca con un término <termino>
    Then la petición se rechaza como inválida
    And no se consume ninguna llamada al proveedor de embeddings

    Examples:
      | termino                        |
      | vacío                          |
      | compuesto solo de espacios     |
      | más largo que el máximo admitido |

  # ─────────────── Búsqueda: fallos de dependencias ───────────────

  Scenario: Un fallo del proveedor de embeddings no se disfraza de KB vacía
    Given un proveedor de embeddings que no responde
    When un usuario realiza una búsqueda
    Then obtiene un error que identifica el fallo del proveedor
    And no una página de resultados vacía

  Scenario: Un vector de dimensión inesperada se rechaza como fallo del proveedor
    Given un proveedor de embeddings que responde con un vector de dimensión distinta a la configurada
    When un usuario realiza una búsqueda
    Then obtiene un error que identifica el fallo del proveedor
    And el vector inválido no llega a compararse contra el corpus

  Scenario: Un fallo de la base de datos no se disfraza de KB vacía
    Given una base de datos que no responde
    When un usuario lista los documentos de la KB
    Then obtiene un error de infraestructura
    And no una página de resultados vacía

  Scenario: Solo participan los vectores del modelo de embeddings configurado
    Given una KB que conserva vectores generados por dos modelos distintos
    When un usuario realiza una búsqueda
    Then los documentos cuyo vector generó el otro modelo no aparecen entre los resultados

  Scenario: Un chunk sin embedding no participa ni rompe la búsqueda
    Given un documento con una sección que quedó sin vector tras la ingesta
    When un usuario busca un término que casaría con esa sección
    Then la búsqueda se completa con normalidad
    And esa sección no aparece entre los resultados

  # ─────────────── Listado y detalle ───────────────

  Scenario: Abrir un documento existente
    Given un uc_id que corresponde a un documento de la KB
    When un usuario pide ese documento
    Then obtiene su título, dominio, package, estado y origen

  Scenario: Un documento sin fecha de actualización se sirve igualmente
    Given un documento de la KB cuya fecha de actualización no consta
    When un usuario pide ese documento
    Then obtiene el documento con el resto de sus datos
    And la fecha de actualización se presenta como ausente, no como error

  Scenario: Abrir un documento inexistente
    Given un uc_id que no corresponde a ningún documento de la KB
    When un usuario pide ese documento
    Then obtiene una respuesta de no encontrado

  Scenario: Un identificador con forma inesperada no rompe la consulta
    Given un uc_id con caracteres especiales que no corresponde a ningún documento
    When un usuario pide ese documento
    Then obtiene una respuesta de no encontrado

  Scenario: Los glosarios son documentos de pleno derecho
    Given una KB que incluye glosarios además de casos de uso
    When un usuario lista los documentos de la KB
    Then los glosarios aparecen entre los resultados

  Scenario: Un glosario se abre por su identificador
    Given un glosario de la KB con su identificador sintético
    When un usuario pide ese documento
    Then obtiene el glosario con sus datos, igual que cualquier otro documento

  Scenario: El listado de documentos es estable entre páginas
    Given una KB con más documentos de los que caben en una página
    When un usuario recorre el listado página a página
    Then ningún documento se repite ni se pierde entre páginas

  Scenario: Listar documentos no requiere el proveedor de embeddings
    Given una configuración de embeddings inservible
    When un usuario lista los documentos de la KB
    Then obtiene el listado con normalidad

  Scenario: Pedir una página más allá del listado
    Given una KB con menos documentos de los que abarca la página pedida
    When un usuario pide esa página del listado
    Then obtiene una página vacía
    And el total sigue reflejando cuántos documentos hay

  # ─────────────── Fronteras de la ventana de recuperación (RN-3) ───────────────

  Scenario Outline: Página solicitada según su posición respecto a la ventana
    Given una búsqueda cuyos resultados caben dentro de la ventana de recuperación
    When el usuario pide la página <pagina>
    Then obtiene <items> y el total sigue siendo el de la ventana

    Examples:
      | pagina               | items                       |
      | primera              | los mejores de la ventana   |
      | última con datos     | el resto de la ventana      |
      | más allá de la ventana | ningún resultado          |
```
