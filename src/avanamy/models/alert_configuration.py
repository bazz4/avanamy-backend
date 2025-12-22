"""
AlertConfiguration model for managing notification settings.

Stores where and how to send alerts for a watched API.
"""

from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import uuid

from avanamy.db.database import Base


class AlertConfiguration(Base):
    """
    Configuration for where to send alerts for a watched API.
    
    Supports multiple alert types:
    - email: Send to email address
    - webhook: POST to URL
    - slack: Send to Slack channel
    """
    __tablename__ = "alert_configurations"

    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Relationships
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    watched_api_id = Column(UUID(as_uuid=True), ForeignKey("watched_apis.id"), nullable=False)

    # Alert type and destination
    alert_type = Column(String, nullable=False)
    """Type of alert: 'email', 'webhook', 'slack'"""
    
    destination = Column(String, nullable=False)
    """Where to send: email address, webhook URL, or slack channel ID"""

    # Alert triggers
    alert_on_breaking_changes = Column(Boolean, nullable=False, default=True)
    """Send alert when breaking changes detected"""
    
    alert_on_non_breaking_changes = Column(Boolean, nullable=False, default=False)
    """Send alert when non-breaking changes detected"""
    
    alert_on_endpoint_failures = Column(Boolean, nullable=False, default=True)
    """Send alert when endpoints start failing"""
    
    alert_on_endpoint_recovery = Column(Boolean, nullable=False, default=False)
    """Send alert when failed endpoints recover"""

    # Status
    enabled = Column(Boolean, nullable=False, default=True)
    """If false, no alerts will be sent from this config"""

    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)
    created_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)

    # Relationships
    tenant = relationship("Tenant")
    watched_api = relationship("WatchedAPI", back_populates="alert_configurations")

    def __repr__(self):
        return f"<AlertConfiguration(id={self.id}, type={self.alert_type}, destination={self.destination})>"