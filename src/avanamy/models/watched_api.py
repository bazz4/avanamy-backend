"""
WatchedAPI model for monitoring external API specs.

This model tracks external APIs that should be polled periodically
for changes. When changes are detected, new versions are automatically
created in the system.
"""

from sqlalchemy import Column, String, Boolean, Integer, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from avanamy.db.database import Base
from avanamy.models.base_model import uuid_pk, uuid_fk, timestamp_created, timestamp_updated
from avanamy.models.mixins import AuditMixin

class WatchedAPI(Base, AuditMixin):
    """
    External API that should be monitored for spec changes.
    
    MVP version: Supports only public APIs (no authentication).
    """
    __tablename__ = "watched_apis"

    id = uuid_pk()
    tenant_id = Column(String(255), ForeignKey("tenants.id"), nullable=False)
    provider_id = uuid_fk("providers", nullable=False)
    api_product_id = uuid_fk("api_products", nullable=False)
    api_spec_id = uuid_fk("api_specs", nullable=True)

    spec_url = Column(String, nullable=False)
    spec_format = Column(String, nullable=True)

    polling_frequency = Column(String, nullable=False, default="daily")
    polling_enabled = Column(Boolean, nullable=False, default=True)

    last_polled_at = Column(DateTime(timezone=True), nullable=True)
    last_successful_poll_at = Column(DateTime(timezone=True), nullable=True)
    last_version_detected = Column(Integer, nullable=True)
    last_spec_hash = Column(String, nullable=True)
    last_error = Column(String, nullable=True)
    consecutive_failures = Column(Integer, nullable=False, default=0)

    status = Column(String, nullable=False, default="active")

    tenant = relationship("Tenant", back_populates="watched_apis")
    provider = relationship("Provider", back_populates="watched_apis")
    api_product = relationship("ApiProduct", back_populates="watched_apis")
    api_spec = relationship("ApiSpec", back_populates="watched_apis")
    alert_configurations = relationship("AlertConfiguration", back_populates="watched_api")
    endpoint_health_checks = relationship("EndpointHealth", back_populates="watched_api")

    def __repr__(self):
        return f"<WatchedAPI(id={self.id}, spec_url={self.spec_url}, status={self.status})>"