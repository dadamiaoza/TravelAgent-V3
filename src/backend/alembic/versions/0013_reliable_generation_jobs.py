"""Add reliable generation job lifecycle fields.

Revision ID: 0013
Revises: 0012
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0013"
down_revision: Union[str, None] = "0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "generation_jobs",
        sa.Column("max_attempts", sa.Integer(), server_default="3", nullable=False),
    )
    op.add_column(
        "generation_jobs",
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "generation_jobs",
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "generation_jobs",
        sa.Column("run_token", sa.UUID(), nullable=True),
    )
    op.add_column(
        "generation_jobs",
        sa.Column("error_code", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "generation_jobs",
        sa.Column("status_version", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "generation_jobs",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.add_column(
        "generation_jobs",
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
    )
    op.create_index(
        "uq_generation_jobs_idempotency_key",
        "generation_jobs",
        ["idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )
    op.create_index(
        "uq_generation_jobs_active_trip",
        "generation_jobs",
        ["trip_id"],
        unique=True,
        postgresql_where=sa.text(
            "status IN ('pending', 'running', 'retry_wait')"
        ),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_generation_jobs_active_trip",
        table_name="generation_jobs",
        postgresql_where=sa.text(
            "status IN ('pending', 'running', 'retry_wait')"
        ),
    )
    op.drop_index(
        "uq_generation_jobs_idempotency_key",
        table_name="generation_jobs",
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )
    op.drop_column("generation_jobs", "idempotency_key")
    op.drop_column("generation_jobs", "updated_at")
    op.drop_column("generation_jobs", "status_version")
    op.drop_column("generation_jobs", "error_code")
    op.drop_column("generation_jobs", "run_token")
    op.drop_column("generation_jobs", "heartbeat_at")
    op.drop_column("generation_jobs", "next_run_at")
    op.drop_column("generation_jobs", "max_attempts")
