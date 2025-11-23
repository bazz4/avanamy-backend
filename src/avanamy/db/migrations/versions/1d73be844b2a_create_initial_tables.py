"""create initial tables

Revision ID: 1d73be844b2a
Revises:
Create Date: 2025-11-22 08:33:10.777616

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "1d73be844b2a"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "api_specs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("version", sa.String(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("original_file_s3_path", sa.String(), nullable=False),
        sa.Column("parsed_schema", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), onupdate=sa.func.now()),
    )

    op.create_table(
        "generation_jobs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "api_spec_id",
            sa.Integer(),
            sa.ForeignKey("api_specs.id", ondelete="CASCADE"),
        ),
        sa.Column("job_type", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("output_metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), onupdate=sa.func.now()),
    )

    op.create_table(
        "documentation_artifacts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "api_spec_id",
            sa.Integer(),
            sa.ForeignKey("api_specs.id", ondelete="CASCADE"),
        ),
        sa.Column("artifact_type", sa.String(), nullable=False),
        sa.Column("s3_path", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "version_history",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "api_spec_id",
            sa.Integer(),
            sa.ForeignKey("api_specs.id", ondelete="CASCADE"),
        ),
        sa.Column("version_label", sa.String(), nullable=False),
        sa.Column("changelog", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("version_history")
    op.drop_table("documentation_artifacts")
    op.drop_table("generation_jobs")
    op.drop_table("api_specs")
