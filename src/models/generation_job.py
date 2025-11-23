from sqlalchemy import Column, Integer, String, ForeignKey, JSON, DateTime
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.db.session import Base

class GenerationJob(Base):
    __tablename__ = "generation_jobs"

    id = Column(Integer, primary_key=True, index=True)
    api_spec_id = Column(Integer, ForeignKey("api_specs.id"), nullable=False)

    job_type = Column(String, nullable=False)
    status = Column(String, nullable=False, default="pending")

    output_metadata = Column(JSON, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    api_spec = relationship("ApiSpec")
