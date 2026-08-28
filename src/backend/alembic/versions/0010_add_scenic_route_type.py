"""Add city/scenic route mode and scenic travel advice fields.

Revision ID: 0010
Revises: 0009
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0010"
down_revision: Union[str, None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "itinerary_days",
        sa.Column("route_type", sa.String(16), nullable=False, server_default="city"),
    )
    op.add_column(
        "itinerary_items",
        sa.Column("route_verified", sa.Boolean(), nullable=True),
    )
    op.add_column(
        "itinerary_items",
        sa.Column("travel_advice", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("itinerary_items", "travel_advice")
    op.drop_column("itinerary_items", "route_verified")
    op.drop_column("itinerary_days", "route_type")