"""app.infra.storage.local — adaptador filesystem local del puerto `Storage` (tarea 08).

`key` la construye el llamante (router/servicio) — este adaptador solo valida que la ruta resultante
no escape `root` (anti path-traversal: un `filename` de usuario con `..` no debe poder escribir/leer
fuera del directorio configurado) antes de tocar el filesystem. IO bloqueante delegada a
`asyncio.to_thread` (sin añadir una dependencia async de filesystem nueva al proyecto).
"""

import asyncio
from pathlib import Path

from app.domain.errors import PortError, Validation


class LocalFilesystemStorage:
    """Adaptador de `Storage` (`app.domain.ports.storage`) sobre un directorio local."""

    def __init__(self, root: str | Path) -> None:
        self._root = Path(root).resolve()

    def _resolve(self, key: str) -> Path:
        """`root / key`, resuelta y comprobada DENTRO de `root` — `Validation` (422) si `key`
        (typicamente derivada de un `filename` de usuario) escapa el directorio raíz."""
        candidate = (self._root / key).resolve()
        if candidate != self._root and self._root not in candidate.parents:
            raise Validation(
                f"key de storage inválida: {key!r}",
                code="storage.path_traversal",
                details={"field": "key", "message": "la key no puede escapar el directorio raíz"},
            )
        return candidate

    async def save(self, key: str, content: bytes, content_type: str) -> None:
        path = self._resolve(key)

        def _write() -> None:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)

        try:
            await asyncio.to_thread(_write)
        except OSError as exc:
            raise PortError(f"fallo al guardar el adjunto: {key}") from exc

    async def get_url_or_path(self, key: str) -> str:
        return str(self._resolve(key))
