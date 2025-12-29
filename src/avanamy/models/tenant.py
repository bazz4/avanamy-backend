from sqlalchemy import Column, String
from sqlalchemy.orm import relationship
from avanamy.db.database import Base
from avanamy.models.base_model import uuid_pk, uuid_fk, timestamp_created, timestamp_updated

class Tenant(Base):
    __tablename__ = "tenants"
    
    id = uuid_pk()
    name = Column(String, nullable=False)
    slug = Column(String, unique=True, nullable=False)
    status = Column(String, nullable=False, default="active")
    
    created_at = timestamp_created()
    updated_at = timestamp_updated()
    created_by_user_id = uuid_fk("users", nullable=True)
    updated_by_user_id = uuid_fk("users", nullable=True)
    
    watched_apis = relationship("WatchedAPI", back_populates="tenant")