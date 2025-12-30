from sqlalchemy import Column, String, ForeignKey   
from sqlalchemy.orm import relationship
from avanamy.db.database import Base
from avanamy.models.base_model import uuid_pk, uuid_fk, timestamp_created, timestamp_updated
import sqlalchemy as sa
from avanamy.models.mixins import AuditMixin

class ApiProduct(Base, AuditMixin):
    __tablename__ = "api_products"

    id = uuid_pk()
    tenant_id = Column(String(255), ForeignKey("tenants.id"), nullable=False)
    provider_id = uuid_fk("providers", nullable=False)

    name = Column(String, nullable=False)
    slug = Column(String, nullable=False)

    __table_args__ = (
        sa.UniqueConstraint(
            "provider_id",
            "slug",
            name="uq_api_products_provider_slug",
        ),
    )

    watched_apis = relationship("WatchedAPI", back_populates="api_product")