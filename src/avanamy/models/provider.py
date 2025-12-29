from sqlalchemy import Column, String, UniqueConstraint
from sqlalchemy.orm import relationship
from avanamy.db.database import Base
from avanamy.models.base_model import uuid_pk, uuid_fk, timestamp_created, timestamp_updated

class Provider(Base):
    """
    Provider = upstream platform whose API a tenant integrates with.
    Examples: DoorDash, Uber Eats, Shopify, Toast, etc.

    - tenant_id NULL  => "global" provider definition (can be shared)
    - tenant_id NOT NULL => tenant-specific provider (override/custom)
    """
    __tablename__ = "providers"

    id = uuid_pk()
    tenant_id = uuid_fk("tenants", nullable=True)
    
    name = Column(String, nullable=False)
    slug = Column(String, nullable=False)
    status = Column(String, nullable=False, server_default="active")

    created_at = timestamp_created()
    updated_at = timestamp_updated()
    created_by_user_id = uuid_fk("users", nullable=True)
    updated_by_user_id = uuid_fk("users", nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "slug",
            name="uq_providers_tenant_slug",
        ),
    )

    watched_apis = relationship("WatchedAPI", back_populates="provider")