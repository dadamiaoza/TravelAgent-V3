"""Checkpointer tables for LangGraph PostgresSaver."""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "checkpoints",
        sa.Column("thread_id", sa.Text(), primary_key=True, nullable=False),
        sa.Column("checkpoint_ns", sa.Text(), primary_key=True, nullable=False, server_default=""),
        sa.Column("checkpoint_id", sa.Text(), primary_key=True, nullable=False),
        sa.Column("parent_checkpoint_id", sa.Text(), nullable=True),
        sa.Column("type", sa.Text(), nullable=True),
        sa.Column("checkpoint", postgresql.JSONB(), nullable=False),
        sa.Column("metadata", postgresql.JSONB(), nullable=False, server_default="{}"),
    )
    op.create_index("checkpoints_thread_id_idx", "checkpoints", ["thread_id"])

    op.create_table(
        "checkpoint_blobs",
        sa.Column("thread_id", sa.Text(), primary_key=True, nullable=False),
        sa.Column("checkpoint_ns", sa.Text(), primary_key=True, nullable=False, server_default=""),
        sa.Column("channel", sa.Text(), primary_key=True, nullable=False),
        sa.Column("version", sa.Text(), primary_key=True, nullable=False),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("blob", sa.LargeBinary(), nullable=True),
    )
    op.create_index("checkpoint_blobs_thread_id_idx", "checkpoint_blobs", ["thread_id"])

    op.create_table(
        "checkpoint_writes",
        sa.Column("thread_id", sa.Text(), primary_key=True, nullable=False),
        sa.Column("checkpoint_ns", sa.Text(), primary_key=True, nullable=False, server_default=""),
        sa.Column("checkpoint_id", sa.Text(), primary_key=True, nullable=False),
        sa.Column("task_id", sa.Text(), primary_key=True, nullable=False),
        sa.Column("idx", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("channel", sa.Text(), nullable=False),
        sa.Column("type", sa.Text(), nullable=True),
        sa.Column("blob", sa.LargeBinary(), nullable=False),
        sa.Column("task_path", sa.Text(), nullable=False, server_default=""),
    )
    op.create_index("checkpoint_writes_thread_id_idx", "checkpoint_writes", ["thread_id"])


def downgrade() -> None:
    op.drop_table("checkpoint_writes")
    op.drop_table("checkpoint_blobs")
    op.drop_table("checkpoints")
