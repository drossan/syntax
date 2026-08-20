"""app.domain.ports.storage — puerto de almacenamiento de adjuntos.

El binario de un `Attachment` no vive en Postgres, solo su metadato + `storage_key` (03/08). `key` la
construye el LLAMANTE (`app.infra.storage.local`, ruta determinista con un identificador único del
adjunto — dos adjuntos con el mismo `filename` al mismo mensaje no colisionan), no el adaptador — el
puerto no decide naming, solo persiste/recupera por la clave dada.

Fase 1: adaptador filesystem local (`LocalFilesystemStorage`); S3/nube diferido — el puerto lo permite
sin cambiar la firma (seam).

Anti-patrón: guardar el binario en la BD; acoplar el dominio a un SDK de nube concreto.
"""

from typing import Protocol


class Storage(Protocol):
    """Puerto de almacenamiento de binarios (adjuntos)."""

    async def save(self, key: str, content: bytes, content_type: str) -> None:
        """Persiste `content` bajo `key`. Un fallo de IO se envuelve en `PortError` — nunca una
        excepción de filesystem/SDK cruda."""
        ...

    async def get_url_or_path(self, key: str) -> str:
        """Ubicación para servir `key`: ruta absoluta local (fase 1) o URL firmada (nube, futuro) —
        el router no necesita saber cuál de las dos es."""
        ...
