from sqlalchemy import Column, String, UniqueConstraint, ForeignKey
from sqlalchemy.orm import relationship
from avanamy.db.database import Base
from avanamy.models.base_model import uuid_pk, uuid_fk, timestamp_created, timestamp_updated
from avanamy.models.mixins import AuditMixin

class Provider(Base, AuditMixin):
    """
    Provider = upstream platform whose API a tenant integrates with.
    Examples: DoorDash, Uber Eats, Shopify, Toast, etc.

    - tenant_id NULL  => "global" provider definition (can be shared)
    - tenant_id NOT NULL => tenant-specific provider (override/custom)
    """
    __tablename__ = "providers"

    id = uuid_pk()
    tenant_id = Column(String(255), ForeignKey("tenants.id"), nullable=False)
    
    name = Column(String, nullable=False)
    slug = Column(String, nullable=False)
    website = Column(String(500), nullable=True)
    logo_url = Column(String(500), nullable=True)
    description = Column(String, nullable=True)
    status = Column(String, nullable=False, server_default="active")
    

    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "slug",
            name="uq_providers_tenant_slug",
        ),
    )

    watched_apis = relationship("WatchedAPI", back_populates="provider")
    api_products = relationship("ApiProduct", back_populates="provider")