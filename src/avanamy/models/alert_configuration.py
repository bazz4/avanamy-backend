"""
AlertConfiguration model for managing notification settings.

Stores where and how to send alerts for a watched API.
"""

from sqlalchemy import Column, String, Boolean
from sqlalchemy.orm import relationship
from avanamy.db.database import Base
from avanamy.models.base_model import uuid_pk, uuid_fk, timestamp_created, timestamp_updated

class AlertConfiguration(Base):
    """
    Configuration for where to send alerts for a watched API.
    
    Supports multiple alert types:
    - email: Send to email address
    - webhook: POST to URL
    - slack: Send to Slack channel
    """
    __tablename__ = "alert_configurations"

    id = uuid_pk()
    tenant_id = uuid_fk("tenants", nullable=False)
    watched_api_id = uuid_fk("watched_apis", nullable=False)

    alert_type = Column(String, nullable=False)
    destination = Column(String, nullable=False)

    alert_on_breaking_changes = Column(Boolean, nullable=False, default=True)
    alert_on_non_breaking_changes = Column(Boolean, nullable=False, default=False)
    alert_on_endpoint_failures = Column(Boolean, nullable=False, default=True)
    alert_on_endpoint_recovery = Column(Boolean, nullable=False, default=False)

    enabled = Column(Boolean, nullable=False, default=True)

    created_at = timestamp_created()
    updated_at = timestamp_updated()
    created_by_user_id = uuid_fk("users", nullable=True)

    tenant = relationship("Tenant")
    watched_api = relationship("WatchedAPI", back_populates="alert_configurations")

    def __repr__(self):
        return f"<AlertConfiguration(id={self.id}, type={self.alert_type}, destination={self.destination})>"