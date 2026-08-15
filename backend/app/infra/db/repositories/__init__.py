"""app.infra.db.repositories — repositorios de persistencia (adaptadores del puerto de dominio).

`BaseRepository` es la base tenant-aware (filtro app-level por `tenant_id`, 1ª línea sobre RLS).
Los repos CONCRETOS que implementan los puertos de `app.domain` nacen en el plan 10.
Anti-patrón: confiar solo en RLS para el aislamiento; exponer entidades ORM crudas al dominio.
"""

from app.infra.db.repositories.base import BaseRepository, TenantScoped

__all__ = ["BaseRepository", "TenantScoped"]
