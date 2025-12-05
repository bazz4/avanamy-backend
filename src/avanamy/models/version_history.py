from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy import ForeignKey
from sqlalchemy import Column, Integer, String, ForeignKey, Text, DateTime
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from avanamy.db.database import Base

class VersionHistory(Base):
    __tablename__ = "version_history"

    id = Column(Integer, primary_key=True, index=True)
    api_spec_id = Column(Integer, ForeignKey("api_specs.id"), nullable=False)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=True)
    version_label = Column(String, nullable=False)
    changelog = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    api_spec = relationship("ApiSpec")
 