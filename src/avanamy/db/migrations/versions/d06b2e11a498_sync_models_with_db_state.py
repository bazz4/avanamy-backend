"""sync_models_with_db_state

Revision ID: d06b2e11a498
Revises: 0f38f020eedc
Create Date: 2025-12-28 17:09:27.752450

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd06b2e11a498'
down_revision: Union[str, Sequence[str], None] = '0f38f020eedc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
