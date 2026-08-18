"""app.domain.entities — entidades y enums propios del dominio (Pydantic v2).

El dominio no importa `app.infra` ni SQLAlchemy (hexagonal, NFR-003): estos tipos son la única fuente de
verdad que ven los servicios. Los enums repiten el **mismo conjunto de valores** que
`app.infra.db.models.enums` (protegido por un test de drift, `tests/test_domain_entities.py`), pero se
definen aquí de forma independiente — no se importan del ORM.
"""
