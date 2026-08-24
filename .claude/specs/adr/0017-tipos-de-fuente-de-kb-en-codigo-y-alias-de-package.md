# 0017. Tipos de fuente de la KB registrados en código + alias de package como configuración

- **Estado**: accepted
- **Fecha**: 2026-08-24
- **Decisores**: Owner.
- **Contexto SDD**: refina [ADR-0010](./0010-rag-pgvector-chunking-h2-tolerante-estado-peso.md) (RAG:
  pgvector + chunking H2 tolerante + peso `estado`). Materializa FR-032, FR-042…FR-044, FR-048. Traza
  [CU-BE-07](../backend/casos-de-uso/CU-BE-07-ingestion-de-la-kb.md). Detalle:
  [`rag-ingestion.md`](../backend/rag-ingestion.md) §1/§2.

## Contexto y planteamiento del problema

El pipeline de ingestión (plan `kb-ingestion`, cerrado) se implementó **entero** contra un formato de
fuente **hipotético**: `<dominio>/uc/UC-*.md` con frontmatter `title`/`domain`/`package`/`uc` y un
bloque `::: info Trazabilidad`. Nunca se verificó contra una fuente real, porque no había ninguna
disponible: se diseñó a partir de una interpretación de `rag-ingestion.md`.

Al aparecer la fuente real, tres hechos verificados invalidaron esa hipótesis:

1. **Otro layout**: los 268 UC no viven bajo `<dominio>/uc/`, sino repartidos **por subdirectorio de
   package** (`packages/<pkg>/docs/aiup/use-cases/UC-*.md`), y los glosarios en una ubicación
   compartida, un fichero plano por dominio.
2. **Otro frontmatter**: solo `id`/`dominio`/`estado`/`traza`. **No hay `title`** (es el primer H1 del
   cuerpo) ni **`package`** (se deriva del subdirectorio); no existe el bloque de Trazabilidad.
3. **El generador de site de la fuente no sirve como intermediario**: produce algo parecido al formato
   hipotético, pero (verificado contra su código) con la negrita del callout en otra posición, los
   valores entre backticks y el `package` con el **nombre de marca del cliente**, no el valor del enum.

El nombre real de cada subdirectorio de package es **vocabulario del cliente**, no del formato: la KB
usa `syntax-*` y la fuente usa otros nombres. Hace falta una traducción, y hace falta decidir **dónde
vive**.

## Decision drivers

- El formato que corre **por defecto** debe ser el que está verificado; que el default sea el hipotético
  significa que un despliegue correcto termina "con éxito" reportando 0 procesados, indistinguible de
  "no había nada que ingerir".
- El producto **no debe llevar puesto el vocabulario de marca de ningún cliente** (ni en código, ni en
  specs, ni en fixtures).
- Un typo en una env var que solo usa la ingestión **no puede tumbar el arranque de toda la app**.
- Sin un **segundo caso real** confirmado, cualquier generalización es especulación.

## Opciones consideradas

1. **Registro de tipos de fuente en código** (un módulo `(load, parse)` por tipo) + alias de package en
   configuración de deployment.
2. **Mapeo declarativo genérico por-tenant**: un YAML que describe dónde está cada campo (globs,
   nombres de claves de frontmatter, reglas de derivación), interpretado en runtime.
3. **Adaptar el parser existente** para que tolere los dos formatos con ramas condicionales.
4. **Depender del generador de site** de la fuente para producir el formato que el parser ya entiende.

## Resultado de la decisión

**Opción 1.** `app/ingestion/sources.py` mantiene un registro `str → SourceType(load, parse,
requires_package_aliases)`:

- `"packages-uc"` → el formato **real verificado**. Es el **default** (`Settings.kb_source_type`).
- `"vitepress-domains"` → el formato hipotético, referenciando `loader.py`/`parser.py` **sin tocarlos**.

Los dos tipos son **implementaciones independientes** que comparten **solo el contrato de datos**
(`RawDoc`/`ParsedUC`/`ParseError`), no detalles internos: nada de importar privados entre módulos.

- **Alias de package = configuración de deployment**, no tabla en código: `KB_PACKAGE_ALIASES`, **JSON
  crudo en un `str`**. No un `dict[str, str]` tipado, porque pydantic-settings lo validaría de forma
  **eager** al construir `Settings()` y un JSON malformado tumbaría el arranque de auth, tickets y todo
  lo demás. Se parsea **donde se usa** y falla como error de uso (código 2) acotado a `make ingest`.
  Por la misma razón `kb_source_type` es `str` y no `Literal`.
- **Sin alias configurados, `packages-uc` no ingiere ningún UC.** Es el comportamiento esperado —fuerza
  a declarar el vocabulario del deployment— pero la CLI **avisa por stderr**, porque un informe con 0
  procesados es indistinguible de un origen vacío legítimo.
- **Solo la forma canónica exacta** del `source_type` se reconoce: `"Packages-UC"` es un valor no
  registrado, no un alias tolerado.
- `requires_package_aliases` es un metadato **del tipo**, no de la CLI: sin él, el aviso de arriba
  exigía un `if source_type == "packages-uc"` hardcodeado, o emitía un falso positivo con
  `vitepress-domains`.

### Confirmación

`app/ingestion/sources.py` + `tests/test_sources.py` (registro y errores), `tests/test_cli.py`
(precedencia argumento>config, códigos de salida 2, aviso de alias) y
`tests/test_pipeline_packages_uc.py` (camino end-to-end real contra Postgres+pgvector, incluida la
transición entre formatos). Plan `kb-source-packages-uc`, tareas `-01`/`-02`/`-03`.

## Consecuencias

- **Buena**: el formato verificado es el de producción por defecto; añadir un tercer tipo es un módulo
  nuevo más una entrada en el registro, sin tocar `pipeline` ni la CLI.
- **Buena**: el producto no contiene ninguna referencia al cliente cuya documentación se verificó.
- **Mala, aceptada**: invertir el default obligó a pasar `source_type="vitepress-domains"` explícito en
  los tests que dependían del anterior. Ninguna aserción cambió.
- **Mala, aceptada — riesgo operacional**: el espacio de nombres de `uc_id` es **compartido** entre
  tipos de fuente, así que **cambiar `KB_SOURCE_TYPE` sobre una BD con corpus reconcilia (borra) los
  documentos del formato anterior**. Es correcto (el origen es la verdad) y está fijado por test, pero
  se dispara con un solo cambio de configuración. Se descartó añadir un guardarraíl por volumen de
  borrado (umbral + flag) para no ampliar el alcance; queda como candidato si el caso se da en real.
- **Deuda explícita — `vitepress-domains` sin fuente real.** Se mantiene como opción de primera clase
  aunque **no corresponde a ninguna fuente confirmada**: es especulación perpetuada en el árbol de
  selección de producción. **Criterio de borrado**: se elimina el tipo (con su `loader.py`/`parser.py` y
  sus tests) en cuanto se cumpla una de estas dos condiciones — (a) el owner confirma que ningún
  despliegue lo usa y que la fuente hipotética no va a existir; o (b) aparece un tercer tipo de fuente
  real, momento en el que mantener dos formatos verificados + uno inventado deja de compensar. Mientras
  tanto, no recibe trabajo nuevo: los planes que amplían la ingestión lo dejan tal cual.

## Pros y contras de las opciones

- **Opción 1 (registro en código, elegida)** — *Pros*: cada formato es un módulo independiente que solo
  comparte el contrato de datos, así que un cambio en uno no puede romper el otro; el punto de
  extensión es explícito (un módulo + una entrada); el tipado y los tests cubren cada par por separado.
  *Contras*: un formato nuevo exige **desplegar código**, no solo configuración; y el registro es un
  punto de acoplamiento que hay que mantener alineado con specs, CU y ADR (mitigado con un test que
  falla si aparece un tercer tipo sin actualizarlos).
- **Opción 2 (mapeo declarativo genérico)** — *Pros*: un tenant nuevo sin desplegar código. *Contras*:
  hoy hay **un** caso real; el segundo formato es una hipótesis sin fuente. Diseñar el lenguaje de
  mapeo sin un segundo caso real es adivinar qué ejes hay que parametrizar, y la parte cara
  (título desde el H1 ignorando fences, derivación del `package` desde la ruta) no es declarativa.
- **Opción 3 (un parser con ramas)** — *Pros*: menos ficheros. *Contras*: acopla dos formatos sin nada
  en común salvo el resultado; cada regla nueva de uno arriesga romper el otro, y el módulo verificado
  quedaría atado al no verificado.
- **Opción 4 (depender del generador de site)** — *Pros*: reutiliza el parser existente. *Contras*: aun
  ejecutándolo, su salida **no** encaja (tres discrepancias verificadas, una de ellas el nombre de marca
  en `package`); y añade otro runtime y otro repo como dependencia de la ingestión.
