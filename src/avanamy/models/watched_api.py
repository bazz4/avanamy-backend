"""
WatchedAPI model for monitoring external API specs.

This model tracks external APIs that should be polled periodically
for changes. When changes are detected, new versions are automatically
created in the system.
"""

from sqlalchemy import Column, String, Boolean, Integer, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import uuid

from avanamy.db.database import Base


class WatchedAPI(Base):
    """
    External API that should be monitored for spec changes.
    
    MVP version: Supports only public APIs (no authentication).
    """
    __tablename__ = "watched_apis"

    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Relationships - link to existing hierarchy
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    provider_id = Column(UUID(as_uuid=True), ForeignKey("providers.id"), nullable=False)
    api_product_id = Column(UUID(as_uuid=True), ForeignKey("api_products.id"), nullable=False)

    # API Configuration
    spec_url = Column(String, nullable=False)
    """URL where the API spec can be fetched (e.g., https://api.stripe.com/openapi.yaml)"""
    
    spec_format = Column(String, nullable=True)
    """Format hint: 'openapi_3.0', 'swagger_2.0', etc. Auto-detected if null."""

    # Polling Configuration
    polling_frequency = Column(String, nullable=False, default="daily")
    """How often to poll: 'hourly', 'daily', 'weekly'"""
    
    polling_enabled = Column(Boolean, nullable=False, default=True)
    """If false, skip this API during polling runs"""

    # Tracking
    last_polled_at = Column(DateTime(timezone=True), nullable=True)
    """Last time we attempted to poll this API"""
    
    last_successful_poll_at = Column(DateTime(timezone=True), nullable=True)
    """Last time we successfully fetched and processed the spec"""
    
    last_version_detected = Column(Integer, nullable=True)
    """Version number of the most recent spec we detected"""
    
    last_spec_hash = Column(String, nullable=True)
    """SHA256 hash of the last fetched spec (to detect changes)"""
    
    last_error = Column(String, nullable=True)
    """Error message from last failed poll attempt"""
    
    consecutive_failures = Column(Integer, nullable=False, default=0)
    """Number of consecutive failed poll attempts"""

    # Status
    status = Column(String, nullable=False, default="active")
    """Status: 'active', 'paused', 'failed', 'deleted'"""

    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)

    # Relationships
    tenant = relationship("Tenant", back_populates="watched_apis")
    provider = relationship("Provider", back_populates="watched_apis")
    api_product = relationship("ApiProduct", back_populates="watched_apis")

    # Relationships for Phase 5
    alert_configurations = relationship("AlertConfiguration", back_populates="watched_api")
    endpoint_health_checks = relationship("EndpointHealth", back_populates="watched_api")

    def __repr__(self):
        return f"<WatchedAPI(id={self.id}, spec_url={self.spec_url}, status={self.status})>"