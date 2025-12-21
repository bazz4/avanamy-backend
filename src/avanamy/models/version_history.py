from sqlalchemy.dialects.postgresql import UUID, JSON
from sqlalchemy import Column, Integer, ForeignKey, DateTime, String
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from avanamy.db.database import Base


class VersionHistory(Base):
    __tablename__ = "version_history"

    id = Column(Integer, primary_key=True, index=True)

    # This ties the version to the spec; tenant comes from api_specs.tenant_id.
    api_spec_id = Column(UUID(as_uuid=True), ForeignKey("api_specs.id"), nullable=False)

    # Simple monotonic integer version: 1, 2, 3, ...
    version = Column(Integer, nullable=False)

    # Optional JSON diff payload (can be None for now)
    diff = Column(JSON, nullable=True)


    # AI-generated summary of changes
    summary = Column(String, nullable=True)
    changelog = Column(String, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    created_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)

    api_spec = relationship("ApiSpec")