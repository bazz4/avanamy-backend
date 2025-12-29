from sqlalchemy.dialects.postgresql import UUID, JSON
from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import relationship
from avanamy.db.database import Base
from avanamy.models.base_model import uuid_fk, timestamp_created

class VersionHistory(Base):
    __tablename__ = "version_history"

    id = Column(Integer, primary_key=True, index=True)
    api_spec_id = uuid_fk("api_specs", nullable=False)

    version = Column(Integer, nullable=False)
    diff = Column(JSON, nullable=True)
    summary = Column(String, nullable=True)
    changelog = Column(String, nullable=True)

    created_at = timestamp_created()
    created_by_user_id = uuid_fk("users", nullable=True)

    api_spec = relationship("ApiSpec")