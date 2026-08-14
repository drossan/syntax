"""app.api — capa de entrada HTTP (adaptador de driving).

GUIÓN (→ tareas 11 y 12)
------------------------
Versionado bajo ``app.api.v1``. Los routers traducen HTTP ↔ dominio: validan con schemas
Pydantic, invocan servicios de ``app.domain`` a través de sus puertos y devuelven el
**envelope** definido en el contrato (`.claude/specs/general/api-contract.md`), incluido el
envelope de error problem+json.

Regla hexagonal: la API depende del dominio, nunca al revés; no contiene reglas de negocio
(esas viven en ``app.domain``). El OpenAPI que genera FastAPI debe ser **⊇** al contrato
(gate de conformidad en el guión maestro, tarea 19).
"""
