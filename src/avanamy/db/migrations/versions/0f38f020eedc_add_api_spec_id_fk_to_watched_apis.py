"""add api_spec_id FK to watched_apis

Revision ID: 0f38f020eedc
Revises: e5e63baf3aa3
Create Date: 2025-12-22 16:59:09.175843

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0f38f020eedc'
down_revision: Union[str, Sequence[str], None] = 'e5e63baf3aa3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add api_spec_id FK to watched_apis."""
    # Add the column
    op.add_column('watched_apis', sa.Column('api_spec_id', sa.UUID(), nullable=True))
    
    # Add foreign key constraint
    op.create_foreign_key(
        'fk_watched_apis_api_spec',
        'watched_apis', 
        'api_specs', 
        ['api_spec_id'], 
        ['id']
    )


def downgrade() -> None:
    """Remove api_spec_id FK from watched_apis."""
    # Drop foreign key
    op.drop_constraint('fk_watched_apis_api_spec', 'watched_apis', type_='foreignkey')
    
    # Drop column
    op.drop_column('watched_apis', 'api_spec_id')