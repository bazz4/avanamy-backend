from sqlalchemy import Column, Integer, String, ForeignKey, DateTime
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.db.session import Base

class DocumentationArtifact(Base):
    __tablename__ = "documentation_artifacts"

    id = Column(Integer, primary_key=True, index=True)
    api_spec_id = Column(Integer, ForeignKey("api_specs.id"), nullable=False)

    artifact_type = Column(String, nullable=False)
    s3_path = Column(String, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    api_spec = relationship("ApiSpec")
