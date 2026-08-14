"""alembic/env.py — entorno de migraciones (async).

GUIÓN (→ tarea 08)
------------------
Qué implementar:
  - ``target_metadata = app.infra.db.base.Base.metadata`` (importa todos los modelos de ``models/`` para
    que el autogenerate los vea).
  - URL de ``settings.DATABASE_URL`` (asyncpg). Modo online **async**: ``async_engine_from_config`` +
    ``connection.run_sync(do_run_migrations)`` (Alembic corre síncrono sobre una conexión async). Modo
    offline estándar.
  - Usar la ``naming_convention`` de ``base.py`` para diffs deterministas.

Las políticas RLS y la extensión ``vector`` NO las autogenera Alembic: van escritas a mano en la
migración (ver ``versions/0001_initial_schema.py``). Anti-patrón: crear el engine en import sin settings;
olvidar importar los modelos (autogenerate vacío).
"""
