"""add version column to documentation_artifacts

Revision ID: 3244ecebfdf5
Revises: b809b5959ecf
Create Date: 2025-12-21 22:10:28.141534

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3244ecebfdf5'
down_revision: Union[str, Sequence[str], None] = 'b809b5959ecf'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add version column to documentation_artifacts."""
    op.add_column('documentation_artifacts', sa.Column('version', sa.String(), nullable=True))


def downgrade() -> None:
    """Remove version column from documentation_artifacts."""
    op.drop_column('documentation_artifacts', 'version')