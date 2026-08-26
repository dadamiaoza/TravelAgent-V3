"""Add user_prompt and must_visit to trips for prompt-driven generation.

Revision ID: 0007
Revises: 0006
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("trips", sa.Column("user_prompt", sa.Text(), nullable=True))
    op.add_column("trips", sa.Column("must_visit", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("trips", "must_visit")
    op.drop_column("trips", "user_prompt")
