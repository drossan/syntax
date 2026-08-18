# Capa de datos del backend, explicada para aprender

> Guía didáctica del plan **`database-foundation`** (9 tareas). No es la spec (esa vive en
> `.claude/specs/`) ni el histórico (eso son los session logs). Aquí está el **qué**, el **por qué** y
> los **conceptos de Python/backend** que aparecen, contados para alguien que está subiendo de nivel.
> Léela de arriba a abajo una vez; luego úsala como índice.

## 1. La foto grande: ¿qué construimos?

El plan anterior dejó la API "encendida" (config, seguridad, logging, `/health/live`). Este plan le pone
**la base de datos de verdad**: las tablas, las migraciones, el aislamiento entre clientes (multi-tenant)
y un endpoint que dice si la DB está lista. En orden:

| Tarea | Qué añade | Idea clave que enseña |
|---|---|---|
| 01 | `Settings.database_url` + `embedding_dim` | config inyectable + validación |
| 02 | `Base` + `naming_convention` + mixins | fundamento ORM determinista |
| 03 | 8 modelos de identidad/RBAC + enums | modelos SQLAlchemy 2, enums nativos |
| 04 | 7 modelos de negocio (con `tenant_id`) | FKs, cascadas, índices, la "marca" RLS |
| 05 | 3 modelos de KB + `vector(1536)` | pgvector, decisión "literal vs config" |
| 06 | Alembic + migración inicial + RLS + rol app | migraciones, extensión, políticas RLS |
| 07 | `session.py` + contexto de tenant | **async**, el *footgun* del pool, RLS efectiva |
| 08 | `BaseRepository` (filtro por tenant) | genéricos (PEP 695), defensa en profundidad |
| 09 | `/health/ready` + `deps.get_db_session` | readiness, `problem+json`, timeouts |

**Multi-tenant** = una sola base de datos sirve a muchos clientes ("tenants") y **nadie ve los datos de
otro**. Ese aislamiento es el hilo conductor de casi todo el plan.

## 2. Configuración inyectable (tarea 01)

`app/core/config.py` usa **pydantic-settings**: una clase `Settings(BaseSettings)` que lee variables de
entorno / `.env` y las **valida y tipa** automáticamente.

```python
database_url: str = "postgresql+asyncpg://syntax_app:syntax_app@localhost:5432/syntax"
embedding_dim: int = Field(default=1536, gt=0)
```

- **Default** = valor si la variable no está. Así `Settings()` se puede construir sin `.env` (útil en tests).
- **`Field(gt=0)`** = *constraint* declarativa: pydantic rechaza `0` o negativos sin que escribas un `if`.
- **`field_validator`** (lo usamos para rechazar un `database_url` vacío `""`): el default cubre la
  *ausencia* de la variable, pero no un `""` explícito; el validador es el único sitio donde cazarlo.
- **"Sin efectos en import"**: la config no se instancia al importar el módulo, sino dentro de
  `get_settings()` (cacheado con `@lru_cache`). Importar un módulo **no** debe conectar a nada ni leer
  secretos: eso hace el código testeable y el arranque predecible.

## 3. El fundamento ORM (tarea 02)

Un **ORM** (SQLAlchemy) te deja trabajar con **clases Python** en vez de escribir SQL a mano. En
SQLAlchemy 2.0 el estilo es:

```python
class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
```

- **`DeclarativeBase`** = la raíz de la que heredan todos los modelos; su `metadata` es el "catálogo" de
  todas las tablas.
- **`Mapped[tipo]` + `mapped_column(...)`** = así se declara una columna con su tipo Python.
- **`naming_convention`** = plantillas para los nombres de constraints/índices
  (`pk_<tabla>`, `fk_<tabla>_<col>_<tabla_ref>`…). Sin esto, los nombres son autogenerados e inestables y
  cada migración genera ruido. Con esto, **los nombres son deterministas** → diffs limpios.
- **Mixin** = una clase pequeña y reutilizable que "inyecta" columnas comunes por herencia.
  `TenantMixin` aporta `tenant_id` y, además, **es la marca semántica** de "esta tabla va bajo RLS".

## 4. Los modelos y los enums (tareas 03-05)

Las **18 tablas** de `data-model.md` en 3 grupos por su frontera de aislamiento:

- **Identidad/RBAC** (8): `tenant`, `user`, `role`… — de sistema, **sin** RLS de fila.
- **Negocio** (7): `ticket`, `message`… — **con** `tenant_id` y **RLS**.
- **KB** (3): `kb_document`, `kb_chunk`, `embedding` — global, compartida, **sin** RLS.

Conceptos que aparecen:

- **Enums nativos de Postgres**: en vez de un texto libre, `ticket.status` solo admite un conjunto fijo
  (`new`, `open`, …). En Python son `enum.Enum`; el helper `pg_enum(...)` usa **`values_callable`** para
  que las etiquetas en la DB sean los *valores* (`"global"`) y no los *nombres* de miembro Python
  (`global_`, porque `global` es palabra reservada). Detalle pequeño, error clásico.
- **Claves foráneas (FK) y borrado en cascada** (`ON DELETE`):
  - `CASCADE`: al borrar el padre se borran los hijos (borrar un ticket borra sus mensajes).
  - `SET NULL`: el hijo sobrevive con la referencia a `NULL` (borrar un usuario no borra sus tickets;
    `requester_id` queda `NULL`). **Obliga a que la columna sea *nullable***.
  - `RESTRICT`: prohíbe borrar el padre si tiene hijos (un tenant no se hard-borra).
- **`vector(1536)` (pgvector)**: la columna de embeddings guarda un vector de 1536 números. Decisión de
  diseño interesante (tarea 05): lo pusimos **literal** en vez de leer `settings.embedding_dim` al
  importar. ¿Por qué? Porque importar los modelos leyendo `Settings` (a) acoplaría el import a que exista
  `JWT_SECRET`, y (b) haría que el *drift-test* nunca detectara un cambio de dimensión (compararía la config
  contra sí misma). Con el literal, un cambio de dimensión no migrado **se detecta**.

## 5. Migraciones con Alembic (tarea 06)

Una **migración** es un script versionado que lleva el esquema de la DB de un estado al siguiente.
**Alembic** las orquesta. Nuestra migración inicial `0001`:

1. `CREATE EXTENSION vector` (necesario **antes** de crear la columna `vector`).
2. `Base.metadata.create_all(...)` — crea las 18 tablas **desde los modelos**. Truco importante: así el
   esquema migrado es **idéntico** a los modelos por construcción → el *drift-test* no puede fallar por una
   transcripción a mano.
3. Lo que Alembic no autogenera, a mano: los **CHECK** de rango (`csat` 1..5, `confidence` 0..1), los
   **GRANTs** al rol de la app, y las **políticas RLS**.

Conceptos:

- **`env.py` async**: Alembic corre síncrono, pero nuestra DB es async (asyncpg). El patrón es
  `connection.run_sync(...)` sobre una conexión async. La URL de migraciones se lee de
  `MIGRATION_DATABASE_URL` (rol **superusuario**), separada de la URL de runtime.
- **Test de *drift***: `compare_metadata(modelos, DB_migrada)` debe dar diff vacío. Si divergen, algo se
  cambió en un sitio y no en el otro. Aprendimos dos cosas al implementarlo:
  1. Alembic **agrupa** los cambios de columna en sublistas → hay que *aplanar* el diff.
  2. Los CHECK viven solo en la migración (no en los modelos) → se **excluyen** del drift (no tienen
     representación en el modelo, así que no pueden "divergir").

## 6. El corazón: aislamiento multi-tenant con RLS (tareas 06-07)

**RLS** (Row-Level Security) = Postgres filtra las filas **por política**, a nivel de base de datos, aunque
la query no ponga el `WHERE`. Es la **defensa en profundidad**: aunque el código olvide filtrar, la DB no
te deja ver filas de otro tenant.

Tres piezas que tienen que encajar (y aquí está el aprendizaje más jugoso):

1. **Un rol dedicado no-superusuario (`syntax_app`)**. Descubrimiento clave: el usuario por defecto
   (`syntax`) es **superusuario** y Postgres **le salta la RLS**. Si la app se conecta como superusuario,
   ¡las políticas no filtran nada! Por eso la app corre como `syntax_app` (`NOSUPERUSER NOBYPASSRLS`).
   El superusuario queda solo para migraciones. (ADR-0016.)

2. **La política**, en las 7 tablas de negocio:
   ```sql
   USING (current_setting('app.bypass_rls', true) = 'on'
          OR tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
   ```
   - `current_setting('app.tenant_id', true)` lee una "variable de sesión" (GUC). El `true` = *missing_ok*:
     devuelve NULL si no está, en vez de lanzar → **fail-closed** (sin contexto, no ves nada).
   - `NULLIF(..., '')`: **bug real que encontramos** en la tarea 07 → tras usar y soltar una conexión del
     pool, el GUC no vuelve a NULL sino a **cadena vacía `''`**, y `''::uuid` *lanzaba*. El `NULLIF` la
     normaliza a NULL → 0 filas, no un error.
   - `bypass_rls = 'on'`: puerta para el rol "global" de Soporte (ver datos de todos los tenants).

3. **El *footgun* del pool** (tarea 07, `session.py`). Un pool **reutiliza conexiones** entre peticiones.
   Si fijaras el tenant con `SET app.tenant_id = ...` a nivel de **sesión**, esa conexión al volver al pool
   **arrastraría** el tenant a la siguiente petición → **fuga entre clientes**. La solución:
   ```python
   async with session.begin():
       await session.execute(text("SELECT set_config('app.tenant_id', :tid, true)"), {"tid": ...})
   ```
   El tercer argumento `true` = **alcance transaccional**: el valor se descarta al cerrar la transacción,
   así que la conexión reutilizada **no** lo arrastra. (Y `SET LOCAL` no admite parámetros → usamos
   `set_config(...)`, que sí.)

   Esto **solo se puede probar contra Postgres real** (un mock no reproduce el pool): por eso los tests de
   la 07 son de **integración**, con `pool_size=1` (fuerza reutilizar la misma conexión), filas
   **commiteadas** y limpieza con `TRUNCATE`.

**async / await en una frase**: como una petición pasa mucho tiempo esperando a la DB, en vez de bloquear
el proceso, Python "suelta" el control (`await`) para atender otras peticiones mientras tanto. El engine,
la sesión y las queries son todos `async`.

## 7. Defensa en profundidad app-level: `BaseRepository` (tarea 08)

RLS es la última línea. La **primera** es filtrar por `tenant_id` en el propio código:

```python
class BaseRepository[T: TenantScoped]:  # PEP 695: genérico "moderno" (Python 3.12)
    async def get(self, entity_id, tenant_id): ...  # WHERE id = ? AND tenant_id = ?
```

- **Genéricos (`[T: TenantScoped]`)**: la clase funciona para *cualquier* modelo de negocio; `T` es el
  tipo concreto (p.ej. `Ticket`). El *bound* `TenantScoped` es un **Protocol** que dice "este tipo tiene
  `id` y `tenant_id`" → mypy verifica el acceso a esas columnas.
- **Por qué dos defensas**: si mañana una query olvida el `WHERE tenant_id`, RLS aún protege; y al revés,
  el filtro app-level protege si algún día alguien se conecta con un rol que salta RLS. Cinturón + tirantes.
- Los tests de la 08 usan a propósito el rol **superusuario** (RLS *apagada*) para demostrar que el filtro
  del repo aísla **por sí solo**, sin depender de RLS.

## 8. Readiness: ¿está la DB lista? (tarea 09)

- **Liveness** (`/health/live`) = "¿el proceso responde?" (no toca la DB).
- **Readiness** (`/health/ready`, alias `/health`) = "¿puede servir tráfico?": DB alcanzable + extensión
  `vector` + la dimensión viva de `embedding.vector` coincide con la config. Si algo falla →
  **503** con cuerpo `application/problem+json` (RFC 9457: `{type, title, status, detail}`).
- **Timeout**: el chequeo está acotado (`asyncio.timeout`) para que una DB colgada dé 503 en vez de dejar
  el endpoint colgado. Es la diferencia entre "no listo" y "no responde".
- `deps.get_db_session` es la *dependency* de FastAPI que cederá una `AsyncSession` a los routers de
  planes futuros.

## 9. Cómo se trabaja aquí (TDD + gates)

Cada tarea siguió el ciclo:

1. **RED**: escribir el test que describe el comportamiento y verlo **fallar** (confirma que el test prueba
   algo real). *(Excepción honesta: en la tarea 09 escribí impl y tests juntos y solo corrí la pasada
   verde; queda anotado en su session log.)*
2. **GREEN**: el código mínimo para que pase.
3. **REFACTOR**: limpiar.
4. **Gates de cierre**: `ruff` (lint + formato) · `mypy --strict` (tipos) · **mutation testing**
   (cosmic-ray) · `/sdd-lint` (artefactos SDD) · `fact-checker` (un agente independiente re-verifica cada
   afirmación contra el código/tests reales).

**Mutation testing** en una frase: introduce "mutantes" en tu código (cambia un `>` por `>=`, un `!=` por
`<`, borra un `not`…) y comprueba que **algún test falla** por cada uno. Un mutante que *sobrevive* = un
comportamiento que ningún test verifica. Nos obligó, por ejemplo, a añadir un caso de test de dimensión
(1024) que cazaba un mutante `!=`→`<` que los otros valores no cazaban. Los ficheros **declarativos**
(modelos, migración) se excluyen del gate (mutarlos da mutantes de bajo valor).

## 10. Comandos útiles (desde `backend/`)

```bash
docker compose up -d db            # levanta Postgres 16 + pgvector (necesario para integración)
make test                          # pytest (unit + integración)
make lint                          # ruff check + ruff format --check
make typecheck                     # mypy --strict
make mutation                      # gate de mutation (acota cosmic-ray.toml al fichero de la tarea)
.venv/bin/alembic upgrade head     # aplica migraciones (necesita MIGRATION_DATABASE_URL, rol superuser)
```

> Los tests de integración crean/reutilizan una DB `syntax_test` y aseguran el rol `syntax_app`
> automáticamente (fixtures en `tests/conftest.py`). Si `db` no está levantado, **fallan con un mensaje
> claro** (no se saltan en silencio).

## 11. Para seguir tirando del hilo

- **Por qué** de cada decisión → `.claude/specs/adr/` (sobre todo **ADR-0006** y **ADR-0016** para RLS,
  **ADR-0010** para pgvector).
- **Qué** exacto (contrato) → `.claude/specs/backend/data-model.md` (las 18 entidades, enums, cascadas, RLS).
- **Cómo se hizo cada tarea** (paso a paso, decisiones, tests) → `.claude/context/backend/backend-database-foundation-0N.md`.
- **Lo siguiente** (plan 10, dominio): repos concretos que implementan puertos, `get_tenant_context`/RBAC,
  y quién puede activar el bypass `global`.
