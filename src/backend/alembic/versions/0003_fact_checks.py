"""Add fact_checks table for fact-check result persistence.

Revision ID: 0003
Revises: 0002
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "fact_checks",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("trip_id", sa.Uuid(), sa.ForeignKey("trips.id", ondelete="SET NULL"), nullable=True),
        sa.Column("itinerary_item_id", sa.Uuid(), sa.ForeignKey("itinerary_items.id", ondelete="SET NULL"), nullable=True),
        sa.Column("poi_name", sa.String(256), nullable=False),
        sa.Column("check_date", sa.Date(), nullable=False),
        sa.Column("risk", sa.String(16), nullable=False),
        sa.Column("risk_type", sa.String(32), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("source", sa.Text(), nullable=True),
        sa.Column("weather", sa.Text(), nullable=True),
        sa.Column("opening_hours", sa.Text(), nullable=True),
        sa.Column("needs_manual_confirmation", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("advice", sa.Text(), nullable=True),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_fact_checks_trip_id", "fact_checks", ["trip_id"])
    op.create_index("ix_fact_checks_check_date", "fact_checks", ["check_date"])


def downgrade() -> None:
    op.drop_index("ix_fact_checks_check_date", table_name="fact_checks")
    op.drop_index("ix_fact_checks_trip_id", table_name="fact_checks")
    op.drop_table("fact_checks")
