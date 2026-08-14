"""app.infra.db — persistencia Postgres (SQLAlchemy async) + Alembic + RLS.

GUIÓN (→ tarea 08: capa DB) — incluye SEEDS (→ tarea 17: ``seed.py``)
--------------------------------------------------------------------
Qué implementar aquí:
  - ``models.py``  → modelos SQLAlchemy 2 (mapped) de las tablas de negocio + RBAC
                     (``Capability``/``Role``/``RoleCapability``), según `data-model` (tarea 03).
  - ``session.py`` → engine async (asyncpg) + factory de sesión; ver footgun ⚠️ abajo.
  - repos          → adaptadores que implementan los puertos de repositorio de ``app.domain``.
  - ``seed.py``    → carga idempotente de seeds/fixtures (entry-point ``python -m app.infra.db.seed``).
  - ``alembic/``   → entorno de migraciones + **políticas RLS** (tablas de negocio) por tenant.
                     La KB es compartida → **sin RLS de tenant**.

⚠️ FOOTGUN (obligatorio en el guión, del design-review):
  ``SET app.tenant_id`` por conexión sobre un **pool asyncpg** es peligroso: una conexión
  reutilizada del pool puede arrastrar el ``tenant_id`` de otra request → fuga cross-tenant.
  El aislamiento es **app-level en repos + RLS**. Al IMPLEMENTAR, EXIGE tests de integración
  contra Postgres real (docker-compose ``db``) que prueben el reset por conexión.

Dependencias: implementa puertos de ``app.domain``; NO expone SQLAlchemy hacia el dominio.
"""
