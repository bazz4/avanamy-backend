"""add api_product_id foreign key and constraints

Revision ID: d71f07d6a761
Revises: 30c8d0dfc72b
Create Date: 2025-12-06 09:24:12.709431

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd71f07d6a761'
down_revision = "30c8d0dfc72b" 
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
