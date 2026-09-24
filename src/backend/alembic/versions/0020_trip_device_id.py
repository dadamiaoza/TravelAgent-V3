"""Bind trips to an anonymous device id.

Revision ID: 0020
Revises: 0019
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0020"
down_revision: Union[str, None] = "0019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("trips", sa.Column("device_id", sa.String(length=64), nullable=True))
    op.create_index("ix_trips_device_id", "trips", ["device_id"])


def downgrade() -> None:
    op.drop_index("ix_trips_device_id", table_name="trips")
    op.drop_column("trips", "device_id")
