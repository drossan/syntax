"""Tests de `app.infra.storage.local.LocalFilesystemStorage` (tarea `backend-routers-core-08`).

Sin Postgres — solo filesystem (usa `tmp_path` de pytest, aislado por test).
"""

import asyncio
from pathlib import Path

import pytest
from app.domain.errors import PortError, Validation
from app.infra.storage.local import LocalFilesystemStorage


async def _read_bytes(path: str) -> bytes:
    return await asyncio.to_thread(Path(path).read_bytes)


async def test_save_then_get_url_or_path_roundtrip(tmp_path: Path) -> None:
    storage = LocalFilesystemStorage(tmp_path)

    await storage.save("t1/m1/a1-informe.pdf", b"contenido", "application/pdf")
    path = await storage.get_url_or_path("t1/m1/a1-informe.pdf")

    assert await _read_bytes(path) == b"contenido"


async def test_save_creates_intermediate_directories(tmp_path: Path) -> None:
    storage = LocalFilesystemStorage(tmp_path)

    await storage.save("a/b/c/file.bin", b"x", "application/octet-stream")

    assert (tmp_path / "a" / "b" / "c" / "file.bin").exists()


async def test_two_keys_with_the_same_filename_do_not_collide(tmp_path: Path) -> None:
    storage = LocalFilesystemStorage(tmp_path)

    await storage.save("t1/m1/a1-informe.pdf", b"primero", "application/pdf")
    await storage.save("t1/m1/a2-informe.pdf", b"segundo", "application/pdf")

    assert await _read_bytes(await storage.get_url_or_path("t1/m1/a1-informe.pdf")) == b"primero"
    assert await _read_bytes(await storage.get_url_or_path("t1/m1/a2-informe.pdf")) == b"segundo"


async def test_save_rejects_a_key_that_escapes_the_root_with_dotdot(tmp_path: Path) -> None:
    """`_resolve` valida y lanza ANTES de escribir (`save` resuelve la key antes de tocar el
    filesystem) — no hace falta comprobar el filesystem fuera de `tmp_path` (compartido entre
    ejecuciones de pytest de toda la máquina, no aislado), basta con que la excepción se dispare."""
    storage = LocalFilesystemStorage(tmp_path)

    with pytest.raises(Validation):
        await storage.save("../../etc/passwd", b"x", "text/plain")

    assert await asyncio.to_thread(lambda: list(tmp_path.iterdir())) == []


async def test_save_rejects_a_key_that_escapes_via_absolute_path(tmp_path: Path) -> None:
    storage = LocalFilesystemStorage(tmp_path)

    with pytest.raises(Validation):
        await storage.save("/etc/passwd", b"x", "text/plain")


async def test_get_url_or_path_rejects_a_key_that_escapes_the_root(tmp_path: Path) -> None:
    storage = LocalFilesystemStorage(tmp_path)

    with pytest.raises(Validation):
        await storage.get_url_or_path("../outside.txt")


async def test_save_wraps_an_io_failure_in_port_error(tmp_path: Path) -> None:
    """`root` es en realidad un FICHERO (no un directorio) — `mkdir(parents=True)` falla con
    `NotADirectoryError` (subclase de `OSError`), el escenario de "disco lleno/permisos" de la tarea."""
    not_a_directory = tmp_path / "im-a-file"
    not_a_directory.write_text("soy un fichero, no un directorio")
    storage = LocalFilesystemStorage(not_a_directory)

    with pytest.raises(PortError):
        await storage.save("sub/dir/file.txt", b"x", "text/plain")
