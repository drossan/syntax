"""Guardia contrato↔OpenAPI, acotada a los schemas de KB (hallazgo E3, tarea `backend-kb-retriever-07`).

`snippet` llevaba roto desde `routers-core` —declarado en `api-contract.yaml`, renderizado por el
front, ausente en la entidad/schema/router de verdad— y se descubrió **por casualidad** al planificar
este plan. Esta es la red que faltaba: compara el OpenAPI que emite `create_app()` con
`api-contract.yaml` para `KBSearchHit`/`KBDocument`, y falla si sus **campos** divergen.

**Acotada a KB a propósito** (ADR-0018): una guardia global de todo el contrato es otro plan, con sus
propios hallazgos que resolver — no lo declara esta tarea.
"""

from pathlib import Path

import yaml
from app.core.config import Settings
from app.main import create_app

_CONTRACT_PATH = Path(__file__).parents[2] / ".claude" / "specs" / "general" / "api-contract.yaml"
_KB_SCHEMAS = ("KBSearchHit", "KBDocument")


def _settings() -> Settings:
    return Settings(_env_file=None, jwt_secret="x" * 32, cors_origins=[])


def _fields(schema: dict[str, object]) -> set[str]:
    properties = schema.get("properties")
    assert isinstance(properties, dict), f"schema sin 'properties': {schema!r}"
    return set(properties.keys())


def test_contract_yaml_declares_the_kb_schemas() -> None:
    """Guardia de la guardia: si el contrato deja de declarar alguno de los dos schemas, que falle
    aquí y no en un `KeyError` opaco más abajo."""
    contract = yaml.safe_load(_CONTRACT_PATH.read_text())
    schemas = contract["components"]["schemas"]

    for name in _KB_SCHEMAS:
        assert name in schemas, f"{name} ya no está en api-contract.yaml"


def test_openapi_kb_schemas_match_the_contract_fields() -> None:
    """Los campos del `KBSearchHit`/`KBDocument` que FastAPI genera coinciden EXACTAMENTE (mismo
    conjunto de nombres) con los del contrato. Ni de más ni de menos: un campo de más sin declarar
    en el contrato es tan drift como uno declarado y ausente del código (el caso real de `snippet`)."""
    contract = yaml.safe_load(_CONTRACT_PATH.read_text())
    contract_schemas = contract["components"]["schemas"]

    openapi = create_app(_settings()).openapi()
    generated_schemas = openapi["components"]["schemas"]

    for name in _KB_SCHEMAS:
        assert name in generated_schemas, f"{name} no aparece en el OpenAPI generado"
        contract_fields = _fields(contract_schemas[name])
        generated_fields = _fields(generated_schemas[name])
        assert generated_fields == contract_fields, (
            f"{name}: el OpenAPI generado ({sorted(generated_fields)}) diverge del contrato "
            f"({sorted(contract_fields)})"
        )
