from sqlalchemy import Column, Integer, String, JSON, ForeignKey
from sqlalchemy.orm import relationship
from avanamy.db.database import Base
from avanamy.models.base_model import uuid_fk
from avanamy.models.mixins import AuditMixin

class GenerationJob(Base, AuditMixin):
    __tablename__ = "generation_jobs"

    id = Column(Integer, primary_key=True, index=True)
    api_spec_id = uuid_fk("api_specs", nullable=False)
    tenant_id = Column(String(255), ForeignKey("tenants.id"), nullable=False)

    job_type = Column(String, nullable=False)
    status = Column(String, nullable=False, default="pending")
    output_metadata = Column(JSON, nullable=True)

    api_spec = relationship("ApiSpec")