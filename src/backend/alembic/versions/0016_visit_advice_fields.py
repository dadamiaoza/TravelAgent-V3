"""Visit-advice fields on itinerary items and source entities.

Revision ID: 0016
Revises: 0015
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0016"
down_revision: Union[str, None] = "0015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("itinerary_items", sa.Column("suggested_duration_h", sa.Float(), nullable=True))
    op.add_column("itinerary_items", sa.Column("best_time", sa.String(length=32), nullable=True))
    op.add_column("itinerary_items", sa.Column("cost_note", sa.String(length=256), nullable=True))
    op.add_column("itinerary_items", sa.Column("opening_hours", sa.String(length=128), nullable=True))
    op.add_column("itinerary_items", sa.Column("visit_tips", sa.Text(), nullable=True))
    op.add_column("itinerary_items", sa.Column("fact_warning", sa.Text(), nullable=True))
    op.add_column("source_entities", sa.Column("visit_tips", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("source_entities", "visit_tips")
    op.drop_column("itinerary_items", "fact_warning")
    op.drop_column("itinerary_items", "visit_tips")
    op.drop_column("itinerary_items", "opening_hours")
    op.drop_column("itinerary_items", "cost_note")
    op.drop_column("itinerary_items", "best_time")
    op.drop_column("itinerary_items", "suggested_duration_h")
