"""add fk + index + unique constraint to api_specs

Revision ID: a409bc1df762
Revises: 64b7882daf80
Create Date: 2025-12-05 16:44:43.497184

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a409bc1df762'
down_revision: Union[str, Sequence[str], None] = '64b7882daf80'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        op.f('ix_api_specs_provider_id'),
        'api_specs',
        ['provider_id'],
        unique=False
    )

    op.create_unique_constraint(
        'uq_api_specs_provider_api_version',
        'api_specs',
        ['tenant_id', 'provider_id', 'api_name', 'version']
    )

    op.create_foreign_key(
        'fk_api_specs_provider_id',
        'api_specs',
        'providers',
        ['provider_id'],
        ['id'],
        ondelete='SET NULL'
    )

def downgrade() -> None:
    op.drop_constraint(
        'fk_api_specs_provider_id',
        'api_specs',
        type_='foreignkey'
    )

    op.drop_constraint(
        'uq_api_specs_provider_api_version',
        'api_specs',
        type_='unique'
    )

    op.drop_index(
        op.f('ix_api_specs_provider_id'),
        table_name='api_specs'
    )
