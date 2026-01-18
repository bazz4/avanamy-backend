"""convert role to enum in organization_members

Revision ID: a84c234eb56e
Revises: e28f119821bf
Create Date: 2026-01-18 18:12:14.104321

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'a84c234eb56e'
down_revision: Union[str, Sequence[str], None] = 'e28f119821bf'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Step 1: Create the new enum type
    member_role_enum = postgresql.ENUM('owner', 'admin', 'developer', 'viewer', name='member_role_enum')
    member_role_enum.create(op.get_bind())
    
    # Step 2: Update any existing 'member' roles to 'developer' (our new default)
    connection = op.get_bind()
    connection.execute(sa.text("""
        UPDATE organization_members 
        SET role = 'developer' 
        WHERE role = 'member'
    """))
    
    # Step 3: Alter the column to use the enum type
    # We use ALTER TYPE with USING to convert the column
    connection.execute(sa.text("""
        ALTER TABLE organization_members 
        ALTER COLUMN role TYPE member_role_enum 
        USING role::member_role_enum
    """))
    
    # Step 4: Set the default value
    op.alter_column('organization_members', 'role',
                    server_default='developer')


def downgrade() -> None:
    """Downgrade schema."""
    # Step 1: Remove the default
    op.alter_column('organization_members', 'role',
                    server_default=None)
    
    # Step 2: Convert column back to varchar
    connection = op.get_bind()
    connection.execute(sa.text("""
        ALTER TABLE organization_members 
        ALTER COLUMN role TYPE VARCHAR(50) 
        USING role::text
    """))
    
    # Step 3: Drop the enum type
    member_role_enum = postgresql.ENUM('owner', 'admin', 'developer', 'viewer', name='member_role_enum')
    member_role_enum.drop(op.get_bind())