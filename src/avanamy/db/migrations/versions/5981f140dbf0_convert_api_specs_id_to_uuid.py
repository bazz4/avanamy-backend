from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from uuid import uuid4

# revision identifiers, used by Alembic.
revision = "5981f140dbf0"
down_revision = "08b0c892187b"  # your last head
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # 1) Add new UUID column on api_specs
    op.add_column(
        "api_specs",
        sa.Column("id_uuid", postgresql.UUID(as_uuid=True), nullable=True),
    )

    # 2) Backfill id_uuid for all existing rows
    rows = conn.execute(sa.text("SELECT id FROM api_specs")).fetchall()
    for (old_id,) in rows:
        conn.execute(
            sa.text(
                "UPDATE api_specs SET id_uuid = :new_id WHERE id = :old_id"
            ),
            {"new_id": str(uuid4()), "old_id": old_id},
        )

    # 3) Add UUID columns to referencing tables + backfill via join
    for table in ("documentation_artifacts", "generation_jobs", "version_history"):
        op.add_column(
            table,
            sa.Column(
                "api_spec_id_uuid", postgresql.UUID(as_uuid=True), nullable=True
            ),
        )
        conn.execute(
            sa.text(
                f"""
                UPDATE {table} t
                SET api_spec_id_uuid = s.id_uuid
                FROM api_specs s
                WHERE t.api_spec_id = s.id
                """
            )
        )

    # 4) Drop existing FKs that point to api_specs.id
    fk_rows = conn.execute(
        sa.text(
            """
            SELECT conrelid::regclass AS table_name,
                   conname
            FROM pg_constraint
            WHERE confrelid = 'api_specs'::regclass
              AND contype = 'f'
            """
        )
    ).fetchall()

    for table_name, conname in fk_rows:
        conn.execute(
            sa.text(
                f'ALTER TABLE {table_name} DROP CONSTRAINT "{conname}"'
            )
        )

    # 5) Drop the existing PK constraint on api_specs
    pk_row = conn.execute(
        sa.text(
            """
            SELECT conname
            FROM pg_constraint
            WHERE conrelid = 'api_specs'::regclass
              AND contype = 'p'
            """
        )
    ).fetchone()

    if pk_row:
        (pk_name,) = pk_row
        conn.execute(
            sa.text(
                f'ALTER TABLE api_specs DROP CONSTRAINT "{pk_name}"'
            )
        )

    # 6) Drop old int columns and rename UUID columns

    # child tables first
    for table in ("documentation_artifacts", "generation_jobs", "version_history"):
        op.drop_column(table, "api_spec_id")
        op.alter_column(
            table,
            "api_spec_id_uuid",
            new_column_name="api_spec_id",
            existing_type=postgresql.UUID(as_uuid=True),
        )

    # then api_specs itself
    op.drop_column("api_specs", "id")
    op.alter_column(
        "api_specs",
        "id_uuid",
        new_column_name="id",
        existing_type=postgresql.UUID(as_uuid=True),
    )

    # 7) Recreate PK + FKs on UUID ids

    op.create_primary_key("pk_api_specs", "api_specs", ["id"])

    op.create_foreign_key(
        "fk_documentation_artifacts_api_spec",
        "documentation_artifacts",
        "api_specs",
        ["api_spec_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_generation_jobs_api_spec",
        "generation_jobs",
        "api_specs",
        ["api_spec_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_version_history_api_spec",
        "version_history",
        "api_specs",
        ["api_spec_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    # Given the complexity and low need to downgrade in dev, we’ll leave this as
    # a no-op. If you *really* need downgrade later, we can write the reverse.
    raise NotImplementedError("Downgrade not supported for UUID PK migration")
