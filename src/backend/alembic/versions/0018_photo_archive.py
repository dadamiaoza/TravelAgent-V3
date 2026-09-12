"""Photo archive tables. Original files are unique per trip; item delete unlinks only.

Revision ID: 0018
Revises: 0017
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0018"
down_revision: Union[str, None] = "0017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "photo_assets",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("trip_id", sa.Uuid(), sa.ForeignKey("trips.id", ondelete="CASCADE"), nullable=False),
        sa.Column("file_path", sa.Text(), nullable=False),
        sa.Column("preview_path", sa.Text(), nullable=True),
        sa.Column("thumbnail_path", sa.Text(), nullable=True),
        sa.Column("original_filename", sa.String(512), nullable=False),
        sa.Column("file_hash", sa.String(64), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=False), nullable=True),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column("exif_json", postgresql.JSONB(), nullable=True),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("trip_id", "file_hash", name="uq_photo_assets_trip_hash"),
    )
    op.create_index("ix_photo_assets_trip_id", "photo_assets", ["trip_id"])

    op.create_table(
        "photo_assignments",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "photo_id",
            sa.Uuid(),
            sa.ForeignKey("photo_assets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "item_id",
            sa.Uuid(),
            sa.ForeignKey("itinerary_items.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("assignment_type", sa.String(32), nullable=False, server_default="time"),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0"),
        sa.Column("evidence_json", postgresql.JSONB(), nullable=True),
        sa.Column("is_confirmed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_photo_assignments_photo_id", "photo_assignments", ["photo_id"])
    op.create_index("ix_photo_assignments_item_id", "photo_assignments", ["item_id"])
    op.create_index(
        "uq_photo_assignments_primary",
        "photo_assignments",
        ["photo_id"],
        unique=True,
        postgresql_where=sa.text("is_primary = true"),
    )

    op.create_table(
        "photo_jobs",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("trip_id", sa.Uuid(), sa.ForeignKey("trips.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("progress", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("stages", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_photo_jobs_trip_id", "photo_jobs", ["trip_id"])


def downgrade() -> None:
    op.drop_index("ix_photo_jobs_trip_id", table_name="photo_jobs")
    op.drop_table("photo_jobs")
    op.drop_index("uq_photo_assignments_primary", table_name="photo_assignments")
    op.drop_index("ix_photo_assignments_item_id", table_name="photo_assignments")
    op.drop_index("ix_photo_assignments_photo_id", table_name="photo_assignments")
    op.drop_table("photo_assignments")
    op.drop_index("ix_photo_assets_trip_id", table_name="photo_assets")
    op.drop_table("photo_assets")
