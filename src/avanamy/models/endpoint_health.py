"""
EndpointHealth model for tracking endpoint availability and performance.

Records health check results for each endpoint in a watched API.
"""

from sqlalchemy import Column, String, Integer, Boolean, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import uuid

from avanamy.db.database import Base


class EndpointHealth(Base):
    """
    Health check results for API endpoints.
    
    Tracks response times, status codes, and availability over time.
    """
    __tablename__ = "endpoint_health"

    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Relationships
    watched_api_id = Column(UUID(as_uuid=True), ForeignKey("watched_apis.id"), nullable=False)

    # Endpoint identification
    endpoint_path = Column(String, nullable=False)
    """The endpoint path, e.g., /v1/users"""
    
    http_method = Column(String, nullable=False)
    """HTTP method: GET, POST, PUT, DELETE, etc."""

    # Health check results
    status_code = Column(Integer, nullable=True)
    """HTTP status code returned (200, 404, 500, etc.)"""
    
    response_time_ms = Column(Integer, nullable=True)
    """Response time in milliseconds"""
    
    is_healthy = Column(Boolean, nullable=False)
    """True if endpoint is responding correctly (2xx or 3xx status)"""
    
    error_message = Column(String, nullable=True)
    """Error message if request failed"""

    # Timestamp
    checked_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    """When this health check was performed"""

    # Relationships
    watched_api = relationship("WatchedAPI", back_populates="endpoint_health_checks")

    def __repr__(self):
        status = "healthy" if self.is_healthy else "unhealthy"
        return f"<EndpointHealth({self.http_method} {self.endpoint_path}: {status})>"