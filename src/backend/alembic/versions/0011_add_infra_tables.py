"""Add amap_cache and generation_jobs tables.

Revision ID: 0011
Revises: 0010
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0011"
down_revision: Union[str, None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "amap_cache",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("cache_type", sa.String(32), nullable=False),
        sa.Column("cache_key", sa.Text(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_amap_cache_cache_type", "amap_cache", ["cache_type"])
    op.create_index("ix_amap_cache_cache_key", "amap_cache", ["cache_key"])

    op.create_table(
        "generation_jobs",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("trip_id", sa.UUID(), sa.ForeignKey("trips.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("progress", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_generation_jobs_trip_id", "generation_jobs", ["trip_id"])


def downgrade() -> None:
    op.drop_table("generation_jobs")
    op.drop_table("amap_cache")