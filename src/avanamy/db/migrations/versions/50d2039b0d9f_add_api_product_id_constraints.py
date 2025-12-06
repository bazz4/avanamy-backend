from alembic import op
import sqlalchemy as sa

revision = "50d2039b0d9f"
down_revision = "d71f07d6a761"
branch_labels = None
depends_on = None


def upgrade():
    # Add foreign key only → index + unique already existed from initial schema
    op.create_foreign_key(
        "fk_api_specs_api_product_id",
        source_table="api_specs",
        referent_table="api_products",
        local_cols=["api_product_id"],
        remote_cols=["id"],
        ondelete="SET NULL"
    )


def downgrade():
    op.drop_constraint("fk_api_specs_api_product_id", "api_specs", type_="foreignkey")
