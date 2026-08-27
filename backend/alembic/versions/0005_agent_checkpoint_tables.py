"""tablas de checkpoint de langgraph-checkpoint-postgres (grafo del agente, ADR-0007).

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-27

Crea las 4 tablas que usa `AsyncPostgresSaver` (`langgraph.checkpoint.postgres.aio`) para persistir el
estado del grafo del agente entre `interrupt()`/`resume` — durabilidad real ante reinicios del proceso
(ADR-0007). Otorga a `syntax_app` (rol runtime, SIN `CREATE`) solo `SELECT`/`INSERT`/`UPDATE`: el
adaptador real solo hace `INSERT ... ON CONFLICT` (upsert), nunca `DELETE` (verificado en
`design-review`, plan `agent-graph`) — mantiene el least-privilege que ya rige el resto del schema
(ADR-0016, migración 0001).

⚠️ **Riesgo documentado** (`design-review`, plan `agent-graph`, ADR-0007 §Consecuencias): el DDL de
abajo se copió del array `MIGRATIONS` de `langgraph.checkpoint.postgres.base` (versión instalada:
`langgraph-checkpoint-postgres==3.1.2`) — un detalle **interno no-público** de la librería (strings
Python crudos, no API estable; la librería solo documenta `AsyncPostgresSaver.setup()` como lo que el
usuario debe llamar). **En cualquier bump de esa dependencia, re-verificar a mano** que `MIGRATIONS` no
cambió antes de asumir que esta migración sigue produciendo el mismo schema. `syntax_app` no tiene
`CREATE`, así que la app NUNCA llama a `.setup()` en runtime (`app/agents/checkpointer.py`) — esta
migración es la única fuente de verdad del schema de estas tablas.

Desviaciones deliberadas del DDL original (no cambian el schema resultante, solo cómo se aplica):
- Colapsa la secuencia incremental de `MIGRATIONS` (10 pasos históricos de la librería, incl. un
  `ALTER ... DROP NOT NULL` que revierte una constraint de un paso anterior de SU historial) en el
  schema FINAL de una sola vez — una migración Alembic representa un estado destino, no un replay de
  la historia interna de otra librería.
- `CREATE INDEX CONCURRENTLY` → `CREATE INDEX` (sin `CONCURRENTLY`): Postgres prohíbe `CONCURRENTLY`
  dentro de una transacción, y Alembic envuelve la migración en una; sin datos todavía en las tablas
  (se crean aquí mismo), no hay contención de bloqueo que `CONCURRENTLY` estuviera evitando.
- No inserta filas en `checkpoint_migrations`: esa tabla solo la lee/escribe `.setup()`, que la app
  nunca llama.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0005"
down_revision: str | Sequence[str] | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = ("checkpoint_migrations", "checkpoints", "checkpoint_blobs", "checkpoint_writes")


def upgrade() -> None:
    op.execute(
        """CREATE TABLE IF NOT EXISTS checkpoint_migrations (
        v INTEGER PRIMARY KEY
    )"""
    )
    op.execute(
        """CREATE TABLE IF NOT EXISTS checkpoints (
        thread_id TEXT NOT NULL,
        checkpoint_ns TEXT NOT NULL DEFAULT '',
        checkpoint_id TEXT NOT NULL,
        parent_checkpoint_id TEXT,
        type TEXT,
        checkpoint JSONB NOT NULL,
        metadata JSONB NOT NULL DEFAULT '{}',
        PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id)
    )"""
    )
    op.execute(
        """CREATE TABLE IF NOT EXISTS checkpoint_blobs (
        thread_id TEXT NOT NULL,
        checkpoint_ns TEXT NOT NULL DEFAULT '',
        channel TEXT NOT NULL,
        version TEXT NOT NULL,
        type TEXT NOT NULL,
        blob BYTEA,
        PRIMARY KEY (thread_id, checkpoint_ns, channel, version)
    )"""
    )
    op.execute(
        """CREATE TABLE IF NOT EXISTS checkpoint_writes (
        thread_id TEXT NOT NULL,
        checkpoint_ns TEXT NOT NULL DEFAULT '',
        checkpoint_id TEXT NOT NULL,
        task_id TEXT NOT NULL,
        idx INTEGER NOT NULL,
        channel TEXT NOT NULL,
        type TEXT,
        blob BYTEA NOT NULL,
        task_path TEXT NOT NULL DEFAULT '',
        PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id, task_id, idx)
    )"""
    )
    op.execute("CREATE INDEX IF NOT EXISTS checkpoints_thread_id_idx ON checkpoints (thread_id)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS checkpoint_blobs_thread_id_idx ON checkpoint_blobs (thread_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS checkpoint_writes_thread_id_idx ON checkpoint_writes (thread_id)"
    )
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON {', '.join(_TABLES)} TO syntax_app")


def downgrade() -> None:
    for table in reversed(_TABLES):
        op.execute(f"DROP TABLE IF EXISTS {table}")
