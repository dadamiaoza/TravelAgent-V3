"""Actual visit stops from photo GPS clusters.

Revision ID: 0019
Revises: 0018
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0019"
down_revision: Union[str, None] = "0018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "visit_stops",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("trip_id", sa.Uuid(), sa.ForeignKey("trips.id", ondelete="CASCADE"), nullable=False),
        sa.Column("lat", sa.Float(), nullable=False),
        sa.Column("lng", sa.Float(), nullable=False),
        sa.Column("place_name", sa.String(255), nullable=False, server_default="未命名停留"),
        sa.Column(
            "linked_item_id",
            sa.Uuid(),
            sa.ForeignKey("itinerary_items.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("status", sa.String(32), nullable=False, server_default="suggested"),
        sa.Column("time_start", sa.DateTime(timezone=False), nullable=True),
        sa.Column("time_end", sa.DateTime(timezone=False), nullable=True),
        sa.Column("evidence_json", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_visit_stops_trip_id", "visit_stops", ["trip_id"])
    op.create_index("ix_visit_stops_linked_item_id", "visit_stops", ["linked_item_id"])
    op.add_column(
        "photo_assignments",
        sa.Column(
            "visit_stop_id",
            sa.Uuid(),
            sa.ForeignKey("visit_stops.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_photo_assignments_visit_stop_id", "photo_assignments", ["visit_stop_id"])


def downgrade() -> None:
    op.drop_index("ix_photo_assignments_visit_stop_id", table_name="photo_assignments")
    op.drop_column("photo_assignments", "visit_stop_id")
    op.drop_index("ix_visit_stops_linked_item_id", table_name="visit_stops")
    op.drop_index("ix_visit_stops_trip_id", table_name="visit_stops")
    op.drop_table("visit_stops")
