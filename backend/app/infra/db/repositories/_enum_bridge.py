"""app.infra.db.repositories._enum_bridge — puente entre enums de dominio y enums ORM.

`app.domain.entities.enums` y `app.infra.db.models.enums` son clases de `enum.Enum` **distintas a
propósito** (el dominio no importa el ORM, NFR-003) que comparten el mismo conjunto de VALORES
(protegido por el test de drift `tests/test_domain_entities.py::test_enum_drift_by_value`). Un mismo
`enum.Enum` (no `str`-mixin) de una clase NO es igual, ni construible por valor, a un miembro de otra
clase con el mismo `.value` — cruzar la frontera ORM↔dominio sin convertir explícitamente produce un
`ValueError` (lectura) o un valor mal serializado hacia Postgres (escritura). Estas dos funciones son
el único punto de conversión, por valor, en ambas direcciones.
"""

import enum


def to_orm[D: enum.Enum, O: enum.Enum](orm_enum_cls: type[O], domain_member: D) -> O:
    """Convierte un miembro de un enum de dominio al miembro equivalente del enum ORM (por `.value`)."""
    return orm_enum_cls(domain_member.value)


def to_domain[D: enum.Enum, O: enum.Enum](domain_enum_cls: type[D], orm_member: O) -> D:
    """Convierte un miembro de un enum ORM al miembro equivalente del enum de dominio (por `.value`)."""
    return domain_enum_cls(orm_member.value)
