from alembic import op
import sqlalchemy as sa
from uuid import uuid4

revision = "30c8d0dfc72b"   # <-- your actual ID here
down_revision = "9eada2af31ba"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()

    # 1. Fetch all valid (provider_id, api_name) pairs
    rows = conn.execute(sa.text("""
        SELECT DISTINCT provider_id, api_name
        FROM api_specs
        WHERE provider_id IS NOT NULL
          AND api_name IS NOT NULL
    """)).fetchall()

    product_map = {}

    # 2. Create/ensure products
    for provider_id, api_name in rows:
        product_id = str(uuid4())
        slug = api_name.lower().replace(" ", "-")

        conn.execute(sa.text("""
            INSERT INTO api_products (id, tenant_id, provider_id, name, slug)
            VALUES (:id, NULL, :provider_id, :name, :slug)
            ON CONFLICT (provider_id, slug) DO NOTHING
        """), {
            "id": product_id,
            "provider_id": provider_id,
            "name": api_name,
            "slug": slug,
        })

        product_map[(provider_id, api_name)] = product_id

    # 3. Backfill api_specs
    for (provider_id, api_name), product_id in product_map.items():
        conn.execute(sa.text("""
            UPDATE api_specs
            SET api_product_id = :product_id
            WHERE provider_id = :provider_id
              AND api_name = :api_name
        """), {
            "product_id": product_id,
            "provider_id": provider_id,
            "api_name": api_name,
        })


def downgrade():
    conn = op.get_bind()
    conn.execute(sa.text("UPDATE api_specs SET api_product_id = NULL"))
    conn.execute(sa.text("DELETE FROM api_products"))
