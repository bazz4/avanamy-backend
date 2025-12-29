from sqlalchemy import Column, Integer, String, JSON
from sqlalchemy.orm import relationship
from avanamy.db.database import Base
from avanamy.models.base_model import uuid_fk, timestamp_created, timestamp_updated

class GenerationJob(Base):
    __tablename__ = "generation_jobs"

    id = Column(Integer, primary_key=True, index=True)
    api_spec_id = uuid_fk("api_specs", nullable=False)
    tenant_id = uuid_fk("tenants", nullable=True)
    
    job_type = Column(String, nullable=False)
    status = Column(String, nullable=False, default="pending")
    output_metadata = Column(JSON, nullable=True)

    created_at = timestamp_created()
    updated_at = timestamp_updated()
    created_by_user_id = uuid_fk("users", nullable=True)
    updated_by_user_id = uuid_fk("users", nullable=True)

    api_spec = relationship("ApiSpec")