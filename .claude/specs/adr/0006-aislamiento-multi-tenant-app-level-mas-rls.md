# 0006. Aislamiento multi-tenant app-level + RLS día 1 (KB global sin RLS)

- **Estado**: accepted
- **Fecha**: 2026-08-11
- **Decisores**: Owner; `grilling` backend (rama 4); `design-review` **#2 mantener** (con guión de footgun).

## Contexto y planteamiento del problema

Cada fila de negocio pertenece a un tenant; una fuga cross-tenant es un fallo grave. ¿El aislamiento se
confía a la capa de aplicación, a la base de datos, o a ambas? La KB es documentación de Syntax
**compartida** entre todos los tenants: ¿también se aísla por fila?

## Decision drivers

- Un solo punto de fallo en el aislamiento es demasiado arriesgado (defensa en profundidad).
- La KB es compartida read-only: aislarla por tenant sería incorrecto.
- El patrón `SET app.tenant_id` sobre un pool async tiene un footgun conocido.

## Opciones consideradas

- **Opción 1** — **App-level (primario)** en los repos (filtro por `tenant_id` del contexto) **+ RLS de
  Postgres (defensa en profundidad) día 1**; KB **global sin RLS**.
- **Opción 2** — Solo **app-level** (sin RLS).
- **Opción 3** — Solo **RLS** (confiar el aislamiento entero a la BD).

## Resultado de la decisión

Elegida: **Opción 1**. Toda query de negocio pasa por repos que filtran por `tenant_id` del contexto
(`get_tenant_context`) **y** las tablas de negocio llevan **RLS** (`USING (tenant_id =
current_setting('app.tenant_id')::uuid)`), fijado por conexión con `SET app.tenant_id`. El ámbito
`global` de Soporte omite el filtro (o usa el tenant del switcher). Las tablas de **KB** (`kb_document`/
`kb_chunk`/`embedding`) **no** llevan RLS de tenant (compartidas); las de identidad/RBAC tampoco (el
aislamiento lo gobierna el RBAC, [[0005-rbac-por-capacidad-y-ambito]]). Un recurso fuera del tenant del
sujeto responde **404** (no revela existencia).

### Confirmación

`rbac.md` §5 + `data-model.md` §6; `alembic/versions/0001_initial_schema.py` (guión `ENABLE RLS` +
`CREATE POLICY tenant_isolation`); **aviso de footgun** en `app/infra/db/session.py` (`SET app.tenant_id`
en pool asyncpg puede filtrar contexto entre conexiones) → **exige tests de integración** de aislamiento
al implementar.

## Consecuencias

- **Buenas**: dos capas independientes; una fuga requiere fallar ambas; 404 no filtra existencia.
- **Malas / coste**: footgun del pool async (contexto entre conexiones reusadas) → tests de integración
  obligatorios; doble mantenimiento (repos + políticas).

## Pros y contras de las opciones

- **Opción 1**: 👍 defensa en profundidad, KB compartida correcta · 👎 footgun del pool; doble capa.
- **Opción 2**: 👍 simple · 👎 un bug de repo = fuga cross-tenant.
- **Opción 3**: 👍 garantía en la BD · 👎 punto único; ORM/pool complican el contexto por request.
