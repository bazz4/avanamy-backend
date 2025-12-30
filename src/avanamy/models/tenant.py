from sqlalchemy import Column, String, Boolean
from sqlalchemy.orm import relationship
from avanamy.db.database import Base
from avanamy.models.base_model import uuid_pk, uuid_fk, timestamp_created, timestamp_updated
from avanamy.models.mixins import AuditMixin

class Tenant(Base, AuditMixin):
    __tablename__ = "tenants"
    
    id = Column(String(255), primary_key=True)
    name = Column(String, nullable=False)
    slug = Column(String, unique=True, nullable=False)
    status = Column(String, nullable=False, default="active")
    is_organization = Column(Boolean, default=False)
    
    watched_apis = relationship("WatchedAPI", back_populates="tenant")