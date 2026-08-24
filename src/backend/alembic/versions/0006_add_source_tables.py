"""Add source_documents and source_entities for guide parsing persistence.

Revision ID: 0006
Revises: 0005
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "source_documents",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("title", sa.String(256), nullable=False, server_default=""),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_table(
        "source_entities",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("source_id", sa.Uuid(), sa.ForeignKey("source_documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("poi_name", sa.String(256), nullable=False),
        sa.Column("day_index", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("seq", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("lat", sa.Float(), nullable=True),
        sa.Column("lng", sa.Float(), nullable=True),
        sa.Column("suggested_duration_h", sa.Float(), nullable=True),
        sa.Column("best_time", sa.String(32), nullable=True),
        sa.Column("cost_estimate", sa.String(256), nullable=True),
    )
    op.create_index("ix_source_documents_user_id", "source_documents", ["user_id"])
    op.create_index("ix_source_entities_source_id", "source_entities", ["source_id"])


def downgrade() -> None:
    op.drop_index("ix_source_entities_source_id", table_name="source_entities")
    op.drop_index("ix_source_documents_user_id", table_name="source_documents")
    op.drop_table("source_entities")
    op.drop_table("source_documents")
