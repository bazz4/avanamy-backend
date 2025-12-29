from sqlalchemy import Column, String
from sqlalchemy.orm import relationship
from avanamy.db.database import Base
from avanamy.models.base_model import uuid_pk, uuid_fk, timestamp_created, timestamp_updated
import sqlalchemy as sa

class ApiProduct(Base):
    __tablename__ = "api_products"

    id = uuid_pk()
    tenant_id = uuid_fk("tenants", nullable=True)
    provider_id = uuid_fk("providers", nullable=False)

    name = Column(String, nullable=False)
    slug = Column(String, nullable=False)

    created_at = timestamp_created()
    updated_at = timestamp_updated()
    created_by_user_id = uuid_fk("users", nullable=True)
    updated_by_user_id = uuid_fk("users", nullable=True)

    __table_args__ = (
        sa.UniqueConstraint(
            "provider_id",
            "slug",
            name="uq_api_products_provider_slug",
        ),
    )

    watched_apis = relationship("WatchedAPI", back_populates="api_product")