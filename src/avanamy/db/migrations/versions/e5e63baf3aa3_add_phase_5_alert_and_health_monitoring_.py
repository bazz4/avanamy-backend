"""add Phase 5 alert and health monitoring tables

Revision ID: e5e63baf3aa3
Revises: 97f78c990d9f
Create Date: 2025-12-22 07:55:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'e5e63baf3aa3'
down_revision: Union[str, Sequence[str], None] = '97f78c990d9f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add Phase 5 alert and health monitoring tables."""
    # Create alert_configurations table
    op.create_table('alert_configurations',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('tenant_id', sa.UUID(), nullable=False),
    sa.Column('watched_api_id', sa.UUID(), nullable=False),
    sa.Column('alert_type', sa.String(), nullable=False),
    sa.Column('destination', sa.String(), nullable=False),
    sa.Column('alert_on_breaking_changes', sa.Boolean(), nullable=False),
    sa.Column('alert_on_non_breaking_changes', sa.Boolean(), nullable=False),
    sa.Column('alert_on_endpoint_failures', sa.Boolean(), nullable=False),
    sa.Column('alert_on_endpoint_recovery', sa.Boolean(), nullable=False),
    sa.Column('enabled', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_by_user_id', sa.UUID(), nullable=True),
    sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ),
    sa.ForeignKeyConstraint(['watched_api_id'], ['watched_apis.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    
    # Create endpoint_health table
    op.create_table('endpoint_health',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('watched_api_id', sa.UUID(), nullable=False),
    sa.Column('endpoint_path', sa.String(), nullable=False),
    sa.Column('http_method', sa.String(), nullable=False),
    sa.Column('status_code', sa.Integer(), nullable=True),
    sa.Column('response_time_ms', sa.Integer(), nullable=True),
    sa.Column('is_healthy', sa.Boolean(), nullable=False),
    sa.Column('error_message', sa.String(), nullable=True),
    sa.Column('checked_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['watched_api_id'], ['watched_apis.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    
    # Create alert_history table
    op.create_table('alert_history',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('tenant_id', sa.UUID(), nullable=False),
    sa.Column('watched_api_id', sa.UUID(), nullable=False),
    sa.Column('alert_config_id', sa.UUID(), nullable=False),
    sa.Column('version_history_id', sa.Integer(), nullable=True),
    sa.Column('alert_reason', sa.String(), nullable=False),
    sa.Column('severity', sa.String(), nullable=False),
    sa.Column('endpoint_path', sa.String(), nullable=True),
    sa.Column('http_method', sa.String(), nullable=True),
    sa.Column('payload', postgresql.JSON(astext_type=sa.Text()), nullable=True),
    sa.Column('status', sa.String(), nullable=False),
    sa.Column('error_message', sa.Text(), nullable=True),
    sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['alert_config_id'], ['alert_configurations.id'], ),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ),
    sa.ForeignKeyConstraint(['version_history_id'], ['version_history.id'], ),
    sa.ForeignKeyConstraint(['watched_api_id'], ['watched_apis.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    
    # Add indexes for common queries
    op.create_index('ix_alert_configurations_watched_api_id', 'alert_configurations', ['watched_api_id'])
    op.create_index('ix_alert_history_watched_api_id', 'alert_history', ['watched_api_id'])
    op.create_index('ix_alert_history_created_at', 'alert_history', ['created_at'])
    op.create_index('ix_endpoint_health_watched_api_id', 'endpoint_health', ['watched_api_id'])
    op.create_index('ix_endpoint_health_checked_at', 'endpoint_health', ['checked_at'])


def downgrade() -> None:
    """Remove Phase 5 tables."""
    op.drop_index('ix_endpoint_health_checked_at', table_name='endpoint_health')
    op.drop_index('ix_endpoint_health_watched_api_id', table_name='endpoint_health')
    op.drop_index('ix_alert_history_created_at', table_name='alert_history')
    op.drop_index('ix_alert_history_watched_api_id', table_name='alert_history')
    op.drop_index('ix_alert_configurations_watched_api_id', table_name='alert_configurations')
    op.drop_table('alert_history')
    op.drop_table('endpoint_health')
    op.drop_table('alert_configurations')