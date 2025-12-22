"""replace version column with version_history_id FK

Revision ID: 97f78c990d9f
Revises: 3244ecebfdf5
Create Date: 2025-12-22 07:41:29.322043

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '97f78c990d9f'
down_revision: Union[str, Sequence[str], None] = '3244ecebfdf5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    # Add new FK column
    op.add_column('documentation_artifacts', 
        sa.Column('version_history_id', sa.Integer(), nullable=True))
    op.create_foreign_key(
        'fk_documentation_artifacts_version_history',
        'documentation_artifacts', 'version_history',
        ['version_history_id'], ['id']
    )
    
    # Drop old version column
    op.drop_column('documentation_artifacts', 'version')

def downgrade():
    # Reverse it
    op.add_column('documentation_artifacts',
        sa.Column('version', sa.String(), nullable=True))
    op.drop_constraint('fk_documentation_artifacts_version_history', 
        'documentation_artifacts', type_='foreignkey')
    op.drop_column('documentation_artifacts', 'version_history_id')
