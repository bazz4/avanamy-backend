"""update github installation id to integer

Revision ID: f30455b6d7d8
Revises: 582bfa228ab8
Create Date: 2026-01-08 17:51:20.808562

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f30455b6d7d8'
down_revision: Union[str, Sequence[str], None] = '582bfa228ab8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    # First, clear any existing data (since we're changing auth model anyway)
    op.execute("UPDATE code_repositories SET github_installation_id = NULL")
    
    # Now alter the column type with explicit USING clause
    op.execute("""
        ALTER TABLE code_repositories 
        ALTER COLUMN github_installation_id 
        TYPE INTEGER 
        USING github_installation_id::integer
    """)
    # ### end Alembic commands ###


def downgrade():
    # Reverse the change
    op.execute("""
        ALTER TABLE code_repositories 
        ALTER COLUMN github_installation_id 
        TYPE VARCHAR(100)
    """)
    # ### end Alembic commands ###
