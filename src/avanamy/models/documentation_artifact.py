from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship
from avanamy.db.database import Base
from avanamy.models.base_model import uuid_fk, timestamp_created

class DocumentationArtifact(Base):
    __tablename__ = "documentation_artifacts"

    id = Column(Integer, primary_key=True, index=True)
    api_spec_id = uuid_fk("api_specs")
    tenant_id = uuid_fk("tenants", nullable=True)
    version_history_id = Column(Integer, ForeignKey("version_history.id"), nullable=True)
    
    artifact_type = Column(String, nullable=False)
    s3_path = Column(String, nullable=False)

    created_at = timestamp_created()
    created_by_user_id = uuid_fk("users", nullable=True)
    updated_by_user_id = uuid_fk("users", nullable=True)

    api_spec = relationship("ApiSpec")
    version_history = relationship("VersionHistory", backref="artifacts")