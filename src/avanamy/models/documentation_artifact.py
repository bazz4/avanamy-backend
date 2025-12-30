from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship
from avanamy.db.database import Base
from avanamy.models.base_model import uuid_fk, timestamp_created
from avanamy.models.mixins import AuditMixin

class DocumentationArtifact(Base, AuditMixin):
    __tablename__ = "documentation_artifacts"

    id = Column(Integer, primary_key=True, index=True)
    api_spec_id = uuid_fk("api_specs")
    tenant_id = Column(String(255), ForeignKey("tenants.id"), nullable=False)
    version_history_id = Column(Integer, ForeignKey("version_history.id"), nullable=True)
    
    artifact_type = Column(String, nullable=False)
    s3_path = Column(String, nullable=False)

    api_spec = relationship("ApiSpec")
    version_history = relationship("VersionHistory", backref="artifacts")