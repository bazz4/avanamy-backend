from alembic import op
import sqlalchemy as sa


revision = "08b0c892187b"
down_revision = "50d2039b0d9f"
branch_labels = None
depends_on = None


def upgrade():
    # 1. Drop old table if it exists
    op.execute("DROP TABLE IF EXISTS version_history CASCADE;")

    # 2. Recreate it with new clean schema
    op.create_table(
        "version_history",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("api_spec_id", sa.Integer, sa.ForeignKey("api_specs.id"), nullable=False),

        # NEW VERSIONING FIELDS
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("diff", sa.JSON, nullable=True),

        # Metadata
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("created_by_user_id", sa.UUID, sa.ForeignKey("users.id"), nullable=True),
    )

    # Index to quickly get the latest version for a spec
    op.create_index(
        "ix_version_history_spec_version",
        "version_history",
        ["api_spec_id", "version"],
        unique=True
    )


def downgrade():
    op.drop_table("version_history")
