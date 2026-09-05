"""Widen opening_hours; Amap/tool text exceeds varchar(128).

Revision ID: 0017
Revises: 0016
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0017"
down_revision: Union[str, None] = "0016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "itinerary_items",
        "opening_hours",
        existing_type=sa.String(length=128),
        type_=sa.Text(),
        existing_nullable=True,
    )
    op.alter_column(
        "itinerary_items",
        "cost_note",
        existing_type=sa.String(length=256),
        type_=sa.Text(),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "itinerary_items",
        "cost_note",
        existing_type=sa.Text(),
        type_=sa.String(length=256),
        existing_nullable=True,
    )
    op.alter_column(
        "itinerary_items",
        "opening_hours",
        existing_type=sa.Text(),
        type_=sa.String(length=128),
        existing_nullable=True,
    )
