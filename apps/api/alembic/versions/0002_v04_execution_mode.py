"""v0.4 — add execution_mode and content_b64.

Revision ID: 0002_v04_execution_mode
Revises: 0001_initial
Create Date: 2026-05-19 20:00:00.000000

Adds two columns required by the v0.4 real agent pipeline:

* ``tasks.execution_mode`` — ``mock`` (default) or ``real``. Set when
  the dispatcher chooses a pipeline branch; the approve / reject
  routes use it to decide whether to enqueue Celery or run the
  in-process mock orchestrator.
* ``task_files.content_b64`` — base64-encoded UTF-8 file content
  staged by the pre-approval pipeline so the post-approval push can
  commit the file without re-opening a sandbox. ``NULL`` for the mock
  pipeline.

Both columns default to safe values so an in-place upgrade does not
break existing rows: ``mock`` for ``execution_mode`` and ``NULL`` for
``content_b64``.

The downgrade is a clean drop; no dependent objects use these columns
outside the API + agent-runner code paths.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002_v04_execution_mode"
down_revision: str | Sequence[str] | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "tasks",
        sa.Column(
            "execution_mode",
            sa.String(length=16),
            nullable=False,
            server_default="mock",
        ),
    )
    op.add_column(
        "task_files",
        sa.Column("content_b64", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("task_files", "content_b64")
    op.drop_column("tasks", "execution_mode")
