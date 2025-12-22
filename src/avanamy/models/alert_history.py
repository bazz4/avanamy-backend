"""
AlertHistory model for tracking sent alerts.

Records every alert attempt with status and error details.
"""

from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID, JSON
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import uuid

from avanamy.db.database import Base


class AlertHistory(Base):
    """
    Historical record of all alerts sent.
    
    Tracks success/failure and links to the reason for the alert.
    """
    __tablename__ = "alert_history"

    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Relationships
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    watched_api_id = Column(UUID(as_uuid=True), ForeignKey("watched_apis.id"), nullable=False)
    alert_config_id = Column(UUID(as_uuid=True), ForeignKey("alert_configurations.id"), nullable=False)
    
    # Optional: Link to specific version if alert is about a change
    version_history_id = Column(Integer, ForeignKey("version_history.id"), nullable=True)

    # Alert details
    alert_reason = Column(String, nullable=False)
    """Reason: 'breaking_change', 'non_breaking_change', 'endpoint_down', 'endpoint_recovered'"""
    
    severity = Column(String, nullable=False)
    """Severity: 'info', 'warning', 'critical'"""
    
    endpoint_path = Column(String, nullable=True)
    """If related to specific endpoint health, the endpoint path"""
    
    http_method = Column(String, nullable=True)
    """If related to endpoint: GET, POST, etc."""

    # Alert payload (for debugging/audit)
    payload = Column(JSON, nullable=True)
    """The actual alert content that was sent"""

    # Status tracking
    status = Column(String, nullable=False, default="pending")
    """Status: 'pending', 'sent', 'failed'"""
    
    error_message = Column(Text, nullable=True)
    """If status='failed', the error message"""
    
    sent_at = Column(DateTime(timezone=True), nullable=True)
    """When the alert was successfully sent"""
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    """When the alert was created/queued"""

    # Relationships
    tenant = relationship("Tenant")
    watched_api = relationship("WatchedAPI")
    alert_config = relationship("AlertConfiguration")
    version_history = relationship("VersionHistory")

    def __repr__(self):
        return f"<AlertHistory(id={self.id}, reason={self.alert_reason}, status={self.status})>"