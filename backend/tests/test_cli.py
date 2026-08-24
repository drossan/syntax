"""Tests de app.ingestion.cli (tarea backend-kb-ingestion-07). `ingest()`/`get_embedding_model()` se
mockean (vía `monkeypatch.setattr` sobre los nombres importados en `cli.py`) — la lógica de negocio ya
la cubre `-06`; aquí solo se prueba el parseo de argumentos, el cableado hacia `pipeline.ingest()` y el
mapeo de resultado/excepción a código de salida. Sin Postgres real: `create_async_engine`/`AsyncSession`
son perezosos (no conectan hasta el primer uso), y `ingest()` mockeado nunca llega a usarlos.
"""

from pathlib import Path

import pytest
from app.core.config import Settings
from app.domain.errors import Conflict, PortError, Validation
from app.infra.db.models.kb import EMBEDDING_DIM_LITERAL
from app.ingestion import cli
from app.ingestion.pipeline import IngestReport

_SUCCESS_REPORT = IngestReport(processed=1, created=1, updated=0, skipped=0, deleted=0)


class _FakeEmbeddingModel:
    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[0.1] * EMBEDDING_DIM_LITERAL for _ in texts]


class _FakeSession:
    """Sesión falsa mínima para probar el `commit()` condicional de `_run()` sin Postgres real."""

    def __init__(self) -> None:
        self.committed = False

    async def __aenter__(self) -> "_FakeSession":
        return self

    async def __aexit__(self, *exc_info: object) -> bool:
        return False

    async def commit(self) -> None:
        self.committed = True


class _FakeEngine:
    async def dispose(self) -> None:
        pass


def _patch_success(monkeypatch: pytest.MonkeyPatch, *, report: IngestReport = _SUCCESS_REPORT):
    calls: dict[str, object] = {}

    async def fake_ingest(path, **kwargs):
        calls["path"] = path
        calls["kwargs"] = kwargs
        return report

    monkeypatch.setattr(cli, "ingest", fake_ingest)
    monkeypatch.setattr(cli, "get_embedding_model", lambda settings: _FakeEmbeddingModel())
    return calls


def _patch_raises(monkeypatch: pytest.MonkeyPatch, exc: Exception):
    async def fake_ingest(path, **kwargs):
        raise exc

    monkeypatch.setattr(cli, "ingest", fake_ingest)
    monkeypatch.setattr(cli, "get_embedding_model", lambda settings: _FakeEmbeddingModel())


def _patch_fake_session(monkeypatch: pytest.MonkeyPatch) -> _FakeSession:
    """Sustituye engine/sessionmaker por dobles — para probar si `_run()` llama a `commit()`."""
    fake_session = _FakeSession()
    monkeypatch.setattr(cli, "create_async_engine", lambda url: _FakeEngine())
    monkeypatch.setattr(cli, "async_sessionmaker", lambda engine, **kwargs: lambda: fake_session)
    return fake_session


# ── camino feliz ──


def test_successful_run_returns_exit_code_0(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_success(monkeypatch)

    exit_code = cli.main([str(tmp_path)])

    assert exit_code == 0


def test_business_failure_returns_exit_code_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_raises(monkeypatch, Validation("uc_id duplicado", code="ingestion.duplicate_uc_id"))

    exit_code = cli.main([str(tmp_path)])

    assert exit_code == 1


def test_a_conflict_from_the_lock_returns_exit_code_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_raises(monkeypatch, Conflict("ya hay una ingestión en curso", code="x"))

    exit_code = cli.main([str(tmp_path)])

    assert exit_code == 1


def test_a_port_error_from_the_writer_or_embedder_returns_exit_code_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_raises(monkeypatch, PortError("fallo real"))

    exit_code = cli.main([str(tmp_path)])

    assert exit_code == 1


# ── errores de uso (código 2) ──


def test_a_nonexistent_path_returns_exit_code_2_and_does_not_invoke_the_pipeline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = _patch_success(monkeypatch)
    missing = tmp_path / "no-existe"

    exit_code = cli.main([str(missing)])

    assert exit_code == 2
    assert calls == {}


def test_a_missing_path_with_no_settings_default_returns_exit_code_2(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _patch_success(monkeypatch)
    monkeypatch.setattr(cli, "get_settings", lambda: type("S", (), {"kb_source_path": ""})())

    exit_code = cli.main([])

    assert exit_code == 2
    assert calls == {}


def test_an_unrecognized_flag_returns_exit_code_2(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_success(monkeypatch)

    exit_code = cli.main(["--flag-inexistente"])

    assert exit_code == 2


def test_help_flag_returns_exit_code_0(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    _patch_success(monkeypatch)

    exit_code = cli.main(["--help"])

    assert exit_code == 0


# ── flags: --only / --dry-run / --reconcile ──


def test_only_flag_is_forwarded_to_the_pipeline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = _patch_success(monkeypatch)

    cli.main([str(tmp_path), "--only", "authoring-and-editor"])

    assert calls["kwargs"]["only_domain"] == "authoring-and-editor"


def test_without_only_flag_only_domain_is_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = _patch_success(monkeypatch)

    cli.main([str(tmp_path)])

    assert calls["kwargs"]["only_domain"] is None


def test_dry_run_flag_is_forwarded_to_the_pipeline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = _patch_success(monkeypatch)

    cli.main([str(tmp_path), "--dry-run"])

    assert calls["kwargs"]["dry_run"] is True


def test_without_dry_run_flag_dry_run_is_false(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = _patch_success(monkeypatch)

    cli.main([str(tmp_path)])

    assert calls["kwargs"]["dry_run"] is False


def test_reconcile_flag_is_forwarded_to_the_pipeline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = _patch_success(monkeypatch)

    cli.main([str(tmp_path), "--reconcile"])

    assert calls["kwargs"]["force_reconcile"] is True


def test_without_reconcile_flag_force_reconcile_is_false(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = _patch_success(monkeypatch)

    cli.main([str(tmp_path)])

    assert calls["kwargs"]["force_reconcile"] is False


# ── resolución de la ruta ──


def test_explicit_path_argument_is_used_over_settings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = _patch_success(monkeypatch)
    other = tmp_path / "otra-ruta"
    other.mkdir()
    monkeypatch.setattr(
        cli,
        "get_settings",
        lambda: Settings(_env_file=None, jwt_secret="x", kb_source_path=str(tmp_path)),
    )

    cli.main([str(other)])

    assert calls["path"] == other


def test_settings_kb_source_path_is_used_when_no_argument_is_given(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = _patch_success(monkeypatch)
    monkeypatch.setattr(
        cli,
        "get_settings",
        lambda: Settings(_env_file=None, jwt_secret="x", kb_source_path=str(tmp_path)),
    )

    cli.main([])

    assert calls["path"] == tmp_path


# ── fallo al construir los puertos ──


def test_a_failure_building_the_embedding_model_returns_exit_code_1_without_a_raw_traceback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def fake_get_embedding_model(settings: object) -> object:
        raise PortError("openai_api_key no configurada")

    monkeypatch.setattr(cli, "get_embedding_model", fake_get_embedding_model)

    exit_code = cli.main([str(tmp_path)])

    assert exit_code == 1
    assert "Traceback" not in capsys.readouterr().err


# ── resumen legible ──


def test_success_prints_a_readable_summary_of_the_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _patch_success(
        monkeypatch,
        report=IngestReport(processed=3, created=2, updated=1, skipped=1, deleted=1),
    )

    cli.main([str(tmp_path)])

    out = capsys.readouterr().out
    assert "3" in out
    assert "creados=2" in out
    assert "actualizados=1" in out
    assert "saltados=1" in out
    assert "reconciliados=1" in out


def test_dry_run_summary_is_marked_as_a_simulation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _patch_success(monkeypatch)

    cli.main([str(tmp_path), "--dry-run"])

    assert "dry-run" in capsys.readouterr().out.lower()


# ── commit condicional de la sesión ──


def test_a_normal_run_commits_the_session(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_success(monkeypatch)
    fake_session = _patch_fake_session(monkeypatch)

    cli.main([str(tmp_path)])

    assert fake_session.committed is True


def test_dry_run_does_not_commit_the_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_success(monkeypatch)
    fake_session = _patch_fake_session(monkeypatch)

    cli.main([str(tmp_path), "--dry-run"])

    assert fake_session.committed is False


# ── excepción inesperada (red de seguridad) ──


def test_an_unexpected_non_domain_exception_returns_exit_code_1_without_a_raw_traceback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _patch_raises(monkeypatch, RuntimeError("algo inesperado"))

    exit_code = cli.main([str(tmp_path)])

    assert exit_code == 1
    assert "Traceback" not in capsys.readouterr().err


# ── end-to-end real (Postgres real vía Docker; EmbeddingModel fake) ──


def test_a_real_end_to_end_run_persists_a_document(
    tmp_path: Path, migrated_database: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sin mockear `ingest`/la sesión: ejercita `main()` -> `_run()` -> `pipeline.ingest()` ->
    `SqlAlchemyKBIndexWriter` completo, contra la BD de test real. Función SÍNCRONA a propósito:
    `cli.main()` gestiona su propio `asyncio.run()` internamente — llamarlo desde un test `async def`
    (con un event loop ya corriendo por pytest-asyncio) rompería con "asyncio.run() cannot be called
    from a running event loop"."""
    import asyncio

    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    uc_dir = tmp_path / "authoring-and-editor" / "uc"
    uc_dir.mkdir(parents=True)
    (uc_dir / "UC-CX-001.md").write_text(
        '---\ntitle: "T"\ndomain: authoring-and-editor\npackage: syntax-cx\nuc: UC-CX-001\n---\n\n'
        "# T\n\n## Comportamiento\n\nTexto.\n\n"
        "::: info Trazabilidad\n- **Estado**: active\n- **Package**: syntax-cx\n:::\n"
    )
    monkeypatch.setattr(
        cli,
        "get_settings",
        lambda: Settings(
            _env_file=None, jwt_secret="x", database_url=migrated_database, openai_api_key="sk-test"
        ),
    )
    monkeypatch.setattr(cli, "get_embedding_model", lambda settings: _FakeEmbeddingModel())

    async def _truncate() -> None:
        engine = create_async_engine(migrated_database)
        try:
            async with engine.begin() as conn:
                await conn.execute(
                    text("TRUNCATE embedding, kb_chunk, kb_document RESTART IDENTITY CASCADE")
                )
        finally:
            await engine.dispose()

    async def _count_uc_cx_001() -> int:
        engine = create_async_engine(migrated_database)
        try:
            async with engine.connect() as conn:
                return (
                    await conn.execute(
                        text("SELECT count(*) FROM kb_document WHERE uc_id = 'UC-CX-001'")
                    )
                ).scalar_one()
        finally:
            await engine.dispose()

    asyncio.run(_truncate())
    try:
        # `--source-type` explícito: esta fixture es del formato hipotético, y el default de la
        # CLI pasó a ser el real verificado (`design-review` #2 del plan kb-source-packages-uc).
        exit_code = cli.main([str(tmp_path), "--source-type", "vitepress-domains"])

        assert exit_code == 0
        assert asyncio.run(_count_uc_cx_001()) == 1
    finally:
        asyncio.run(_truncate())


# ── selección del tipo de fuente (tarea backend-kb-source-packages-uc-03) ──


def _settings(tmp_path: Path, **overrides: object) -> Settings:
    return Settings(_env_file=None, jwt_secret="x", kb_source_path=str(tmp_path), **overrides)  # type: ignore[arg-type]


def test_the_default_source_type_is_the_real_verified_format(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Escenario añadido: `El tipo de fuente por defecto es el formato real verificado` — una config
    que no dice nada usa `packages-uc`, no el formato hipotético (`design-review` #2)."""
    calls = _patch_success(monkeypatch)
    _patch_fake_session(monkeypatch)
    monkeypatch.setattr(cli, "get_settings", lambda: _settings(tmp_path))

    exit_code = cli.main([str(tmp_path)])

    assert exit_code == 0
    assert calls["kwargs"]["source_type"] == "packages-uc"


def test_the_cli_argument_takes_precedence_over_the_configured_source_type(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Escenario añadido: `El argumento de la CLI tiene precedencia sobre la configuración` — mismo
    patrón que `path` vs `settings.kb_source_path`."""
    calls = _patch_success(monkeypatch)
    _patch_fake_session(monkeypatch)
    monkeypatch.setattr(
        cli, "get_settings", lambda: _settings(tmp_path, kb_source_type="packages-uc")
    )

    exit_code = cli.main([str(tmp_path), "--source-type", "vitepress-domains"])

    assert exit_code == 0
    assert calls["kwargs"]["source_type"] == "vitepress-domains"


def test_the_configured_source_type_is_used_when_the_argument_is_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = _patch_success(monkeypatch)
    _patch_fake_session(monkeypatch)
    monkeypatch.setattr(
        cli, "get_settings", lambda: _settings(tmp_path, kb_source_type="vitepress-domains")
    )

    exit_code = cli.main([str(tmp_path)])

    assert exit_code == 0
    assert calls["kwargs"]["source_type"] == "vitepress-domains"


@pytest.mark.parametrize(
    "source_type",
    [
        pytest.param("no-existe", id="un nombre que no existe"),
        pytest.param("Packages-UC", id="la misma con otra caja"),
    ],
)
def test_an_unregistered_source_type_is_a_usage_error(
    source_type: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """CU extensión **1g** + `Scenario Outline: El tipo de fuente solo se reconoce en su forma
    canónica`: código **2** (error de uso), no 1, y sin tocar la base de datos."""
    calls = _patch_success(monkeypatch)
    monkeypatch.setattr(cli, "get_settings", lambda: _settings(tmp_path))

    exit_code = cli.main([str(tmp_path), "--source-type", source_type])

    assert exit_code == 2
    assert calls == {}
    assert source_type in capsys.readouterr().err


def test_an_unregistered_source_type_never_leaks_a_raw_traceback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Escenario añadido: `Un tipo de fuente desconocido no expone una traza cruda al operador`."""
    _patch_success(monkeypatch)
    monkeypatch.setattr(cli, "get_settings", lambda: _settings(tmp_path))

    cli.main([str(tmp_path), "--source-type", "no-existe"])

    stderr = capsys.readouterr().err
    assert "Traceback" not in stderr
    assert "packages-uc" in stderr and "vitepress-domains" in stderr


def test_invalid_package_alias_json_is_a_usage_error_scoped_to_the_ingestion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """CU extensión **1m**: el JSON de alias se valida **donde se usa**, no al construir `Settings`
    (si no, un typo tumbaría el arranque de toda la app). Código 2, acotado a la ingestión."""
    calls = _patch_success(monkeypatch)
    monkeypatch.setattr(
        cli, "get_settings", lambda: _settings(tmp_path, kb_package_aliases="{no es json")
    )

    exit_code = cli.main([str(tmp_path)])

    assert exit_code == 2
    assert calls == {}
    assert "alias" in capsys.readouterr().err.lower()


@pytest.mark.parametrize(
    "raw_aliases",
    [
        pytest.param('["a", "b"]', id="una lista, no un objeto"),
        pytest.param('"solo-una-cadena"', id="un escalar, no un objeto"),
        pytest.param('{"vendor-core": 1}', id="un valor no textual"),
        pytest.param('{"vendor-core": null}', id="un valor nulo"),
        pytest.param('{"vendor-core": ["syntax-core"]}', id="un valor que es una lista"),
    ],
)
def test_package_alias_json_that_is_not_an_object_of_strings_is_a_usage_error(
    raw_aliases: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Frontera de 1m: JSON **válido** pero con la forma equivocada no sirve como tabla de traducción.

    Un valor no textual importa de verdad: sin validarlo, llegaría al parser como alias y de ahí a
    `Package(...)`, que es justo el "error inesperado" que 1h existe para evitar.
    """
    calls = _patch_success(monkeypatch)
    monkeypatch.setattr(
        cli, "get_settings", lambda: _settings(tmp_path, kb_package_aliases=raw_aliases)
    )

    assert cli.main([str(tmp_path)]) == 2
    assert calls == {}


def test_blank_package_alias_config_is_treated_as_no_aliases(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Solo espacios en blanco ≡ sin configurar: no es un JSON inválido, es que no hay alias."""
    calls = _patch_success(monkeypatch)
    _patch_fake_session(monkeypatch)
    monkeypatch.setattr(cli, "get_settings", lambda: _settings(tmp_path, kb_package_aliases="   "))

    assert cli.main([str(tmp_path)]) == 0
    assert calls["kwargs"]["package_aliases"] == {}


def test_valid_package_alias_json_reaches_the_pipeline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = _patch_success(monkeypatch)
    _patch_fake_session(monkeypatch)
    monkeypatch.setattr(
        cli,
        "get_settings",
        lambda: _settings(tmp_path, kb_package_aliases='{"vendor-core": "syntax-core"}'),
    )

    exit_code = cli.main([str(tmp_path)])

    assert exit_code == 0
    assert calls["kwargs"]["package_aliases"] == {"vendor-core": "syntax-core"}


def test_a_source_type_that_needs_aliases_warns_when_none_are_configured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """CU `Sin ningún alias configurado no se ingiere nada y se avisa` (extensión **1l**): sin el
    aviso, `procesados=0` es indistinguible de un origen vacío legítimo (4b)."""
    _patch_success(monkeypatch)
    _patch_fake_session(monkeypatch)
    monkeypatch.setattr(cli, "get_settings", lambda: _settings(tmp_path))

    exit_code = cli.main([str(tmp_path)])

    assert exit_code == 0
    assert "alias" in capsys.readouterr().err.lower()


def test_a_source_type_that_does_not_need_aliases_never_warns_about_them(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """CU `Un tipo de fuente que no usa alias no dispara el aviso de alias vacío` — el falso positivo
    que evita el metadato `requires_package_aliases` del descriptor."""
    _patch_success(monkeypatch)
    _patch_fake_session(monkeypatch)
    monkeypatch.setattr(
        cli, "get_settings", lambda: _settings(tmp_path, kb_source_type="vitepress-domains")
    )

    exit_code = cli.main([str(tmp_path)])

    assert exit_code == 0
    assert "alias" not in capsys.readouterr().err.lower()


def test_no_warning_when_the_aliases_are_configured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _patch_success(monkeypatch)
    _patch_fake_session(monkeypatch)
    monkeypatch.setattr(
        cli,
        "get_settings",
        lambda: _settings(tmp_path, kb_package_aliases='{"vendor-core": "syntax-core"}'),
    )

    exit_code = cli.main([str(tmp_path)])

    assert exit_code == 0
    assert "alias" not in capsys.readouterr().err.lower()
