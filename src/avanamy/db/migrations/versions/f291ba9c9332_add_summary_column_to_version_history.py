"""add summary column to version_history

Revision ID: f291ba9c9332
Revises: cdf07b3b39b3
Create Date: 2025-12-21 10:20:40.492267

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f291ba9c9332'
down_revision: Union[str, Sequence[str], None] = 'cdf07b3b39b3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add summary column to version_history for AI-generated change summaries."""
    op.add_column('version_history', sa.Column('summary', sa.String(), nullable=True))


def downgrade() -> None:
    """Remove summary column from version_history."""
    op.drop_column('version_history', 'summary')