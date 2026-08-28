"""Add Amap POI identity fields to itinerary_items.

Revision ID: 0009
Revises: 0008
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("itinerary_items", sa.Column("amap_poi_id", sa.String(128), nullable=True))
    op.add_column("itinerary_items", sa.Column("poi_address", sa.Text(), nullable=True))
    op.add_column("itinerary_items", sa.Column("poi_type", sa.String(256), nullable=True))


def downgrade() -> None:
    op.drop_column("itinerary_items", "poi_type")
    op.drop_column("itinerary_items", "poi_address")
    op.drop_column("itinerary_items", "amap_poi_id")
