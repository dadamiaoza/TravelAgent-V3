"""Add route_polyline to itinerary_items for real route drawing.

Revision ID: 0004
Revises: 0003
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "itinerary_items",
        sa.Column("route_polyline", postgresql.JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("itinerary_items", "route_polyline")
