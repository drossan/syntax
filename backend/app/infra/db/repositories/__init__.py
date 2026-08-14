"""app.infra.db.repositories — adaptadores SQLAlchemy de los puertos de repositorio.

GUIÓN (→ tarea 08)
------------------
Stubs que implementan las interfaces de ``app.domain.ports.repositories`` con SQLAlchemy 2 async. Un
adaptador por puerto; reciben la ``AsyncSession`` por inyección (de ``app.core.deps``).

Reglas:
  - **Aislamiento app-level (primario)**: toda query de una tabla de negocio **filtra por ``tenant_id``**
    del contexto (``get_tenant_context``). Es la primera línea; RLS (políticas Postgres) es la segunda.
  - Soporte con capacidad de ámbito ``global`` (02 §5): el adaptador omite el filtro (o usa el tenant del
    switcher para escribir en nombre de un cliente).
  - **KB** (``KBRepository``): sin filtro de tenant (KB global, sin RLS).
  - Traducen entre modelos SQLAlchemy (``app.infra.db.models``) y tipos de dominio; **no** devuelven
    modelos ORM hacia el dominio.
  - ``KBRepository.upsert_document`` es idempotente por ``uc_id`` y reconcilia huérfanos (04).

Anti-patrón: olvidar el filtro ``tenant_id`` (confiar solo en RLS es un footgun, ver ``session.py``);
devolver entidades ORM crudas al dominio; abrir su propia sesión/engine.
"""
