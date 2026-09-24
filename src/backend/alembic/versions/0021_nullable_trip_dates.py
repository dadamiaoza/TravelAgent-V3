"""Allow undated trip drafts.

Revision ID: 0021
Revises: 0020
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0021"
down_revision: Union[str, None] = "0020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("trips", "start_date", existing_type=sa.Date(), nullable=True)
    op.alter_column("trips", "end_date", existing_type=sa.Date(), nullable=True)


def downgrade() -> None:
    op.execute("UPDATE trips SET start_date = DATE '1970-01-01' WHERE start_date IS NULL")
    op.execute("UPDATE trips SET end_date = DATE '1970-01-01' WHERE end_date IS NULL")
    op.alter_column("trips", "start_date", existing_type=sa.Date(), nullable=False)
    op.alter_column("trips", "end_date", existing_type=sa.Date(), nullable=False)
