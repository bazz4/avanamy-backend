"""add changelog column to version_history

Revision ID: cdf07b3b39b3
Revises: 5981f140dbf0
Create Date: 2025-12-06 19:04:18.340235

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'cdf07b3b39b3'
down_revision: Union[str, Sequence[str], None] = '5981f140dbf0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.add_column(
        "version_history",
        sa.Column("changelog", sa.String(), nullable=True),
    )

def downgrade() -> None:
    op.drop_column("version_history", "changelog")