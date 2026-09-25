"""Store destination timezone and an optional explicit cover photo.

Revision ID: 0022
Revises: 0021
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0022"
down_revision: Union[str, None] = "0021"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("trips", sa.Column("timezone", sa.String(length=64), nullable=True))
    op.add_column("trips", sa.Column("cover_photo_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_trips_cover_photo_id",
        "trips",
        "photo_assets",
        ["cover_photo_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_trips_cover_photo_id", "trips", type_="foreignkey")
    op.drop_column("trips", "cover_photo_id")
    op.drop_column("trips", "timezone")
