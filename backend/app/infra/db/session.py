"""app.infra.db.session — engine async + factory de sesión + contexto RLS.

GUIÓN (→ tarea 08)
------------------
Qué implementar:
  - ``create_async_engine(settings.DATABASE_URL)`` (driver asyncpg) + ``async_sessionmaker`` (expire_on_
    commit=False). Sin efectos en import: se construyen desde el factory/deps con ``get_settings()``.
  - ``get_session()`` → ``AsyncSession`` por request (lo inyecta ``app.core.deps.get_db_session``).
  - **Contexto de tenant para RLS**: al abrir la transacción de una request, fijar
    ``SET LOCAL app.tenant_id = '<uuid>'`` (o ``NULL``/bypass para Soporte con capacidad ``global``).
    Las políticas de ``alembic`` filtran ``USING (tenant_id = current_setting('app.tenant_id')::uuid)``.

⚠️ GUIÓN DE RIESGO (footgun — obligatorio, del design-review):
  ``SET app.tenant_id`` a nivel de CONEXIÓN sobre un **pool asyncpg** es peligroso: el pool **reutiliza
  conexiones** entre requests, así que un ``SET`` no reseteado **arrastra el ``tenant_id`` de otra
  request → fuga cross-tenant**. Mitigaciones:
    - usar ``SET LOCAL`` **dentro de la transacción** (alcance transaccional, se descarta al COMMIT/
      ROLLBACK), NO ``SET`` de sesión; o
    - resetear explícitamente (``RESET app.tenant_id``) en el checkin de la conexión al pool.
  El aislamiento primario sigue siendo **app-level en los repos** (filtro por ``tenant_id``); RLS es
  defensa en profundidad. **Al IMPLEMENTAR, EXIGE tests de integración contra Postgres real**
  (docker-compose ``db``) que prueben que una conexión reutilizada NO ve datos de otro tenant — un mock
  no caza este fallo.

Contrato: ``get_session()`` + el helper que fija/limpia ``app.tenant_id``. Anti-patrón: ``SET`` de sesión
sin reset; engine global creado en import; compartir una sesión entre requests.
"""
