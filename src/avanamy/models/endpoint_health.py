"""
EndpointHealth model for tracking endpoint availability and performance.

Records health check results for each endpoint in a watched API.
"""

from sqlalchemy import Column, String, Integer, Boolean, DateTime
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from avanamy.db.database import Base
from avanamy.models.base_model import uuid_pk, uuid_fk, timestamp_created

class EndpointHealth(Base):
    """
    Health check results for API endpoints.
    
    Tracks response times, status codes, and availability over time.
    """
    __tablename__ = "endpoint_health"

    id = uuid_pk()
    watched_api_id = uuid_fk("watched_apis", nullable=False)

    endpoint_path = Column(String, nullable=False)
    http_method = Column(String, nullable=False)

    status_code = Column(Integer, nullable=True)
    response_time_ms = Column(Integer, nullable=True)
    is_healthy = Column(Boolean, nullable=False)
    error_message = Column(String, nullable=True)

    checked_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    watched_api = relationship("WatchedAPI", back_populates="endpoint_health_checks")

    def __repr__(self):
        status = "healthy" if self.is_healthy else "unhealthy"
        return f"<EndpointHealth({self.http_method} {self.endpoint_path}: {status})>"