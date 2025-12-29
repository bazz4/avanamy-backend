"""
AlertHistory model for tracking sent alerts.

Records every alert attempt with status and error details.
"""

from sqlalchemy import Column, ForeignKey, String, Integer, DateTime, Text
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import relationship
from avanamy.db.database import Base
from avanamy.models.base_model import uuid_pk, uuid_fk, timestamp_created

class AlertHistory(Base):
    """
    Historical record of all alerts sent.
    
    Tracks success/failure and links to the reason for the alert.
    """
    __tablename__ = "alert_history"

    id = uuid_pk()
    tenant_id = uuid_fk("tenants", nullable=False)
    watched_api_id = uuid_fk("watched_apis", nullable=False)
    alert_config_id = uuid_fk("alert_configurations", nullable=False)
    version_history_id = Column(Integer, ForeignKey("version_history.id"), nullable=True)

    alert_reason = Column(String, nullable=False)
    severity = Column(String, nullable=False)
    endpoint_path = Column(String, nullable=True)
    http_method = Column(String, nullable=True)

    payload = Column(JSON, nullable=True)
    status = Column(String, nullable=False, default="pending")
    error_message = Column(Text, nullable=True)
    
    sent_at = Column(DateTime(timezone=True), nullable=True)
    created_at = timestamp_created()

    tenant = relationship("Tenant")
    watched_api = relationship("WatchedAPI")
    alert_config = relationship("AlertConfiguration")
    version_history = relationship("VersionHistory")

    def __repr__(self):
        return f"<AlertHistory(id={self.id}, reason={self.alert_reason}, status={self.status})>"