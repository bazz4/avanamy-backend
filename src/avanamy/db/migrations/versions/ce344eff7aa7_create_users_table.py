"""Create users table

This migration introduces the foundational `users` table.  
It will be referenced by other tables (tenants, providers, api_specs, etc.)  
to track who created or updated each record.

We add this FIRST because later migrations will create foreign keys to users.id.

Revision ID: <AUTOFILLED_BY_ALEMBIC>
Revises: 5ed13436ca15
Create Date: <AUTOFILLED_BY_ALEMBIC>
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# Alembic identifiers
revision = 'ce344eff7aa7'
down_revision = '5ed13436ca15'
branch_labels = None
depends_on = None


def upgrade():
    # --- Create users table -----------------------------------------------
    # This is the foundation for attribution (created_by / updated_by)
    # across all business entities.
    op.create_table(
        'users',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),

        # tenant_id is NULLABLE because:
        # - system users may exist with no tenant
        # - admin / internal actions may not belong to any tenant
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=True),

        # Basic identity fields (email, name)
        sa.Column('email', sa.String(), unique=True, nullable=False),
        sa.Column('name', sa.String(), nullable=True),

        # Simple role system (future enhancement)
        sa.Column('role', sa.String(), nullable=False, server_default='member'),

        # Whether this user is active (soft-delete flag)
        sa.Column('active', sa.Boolean(), nullable=False, server_default=sa.text('TRUE')),

        # Timestamps for auditing
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('NOW()')),

        # Foreign key constraint to tenants.id (nullable)
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='SET NULL'),
    )

    # Create a basic index on tenant_id for common queries
    op.create_index('ix_users_tenant_id', 'users', ['tenant_id'])


def downgrade():
    # Reverse all operations in upgrade()
    op.drop_index('ix_users_tenant_id', table_name='users')
    op.drop_table('users')
