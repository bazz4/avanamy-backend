from sqlalchemy import Column, String, Boolean
from avanamy.db.database import Base
from avanamy.models.base_model import uuid_pk, uuid_fk, timestamp_created, timestamp_updated

class User(Base):
    __tablename__ = "users"

    id = uuid_pk()
    tenant_id = uuid_fk("tenants", nullable=True)

    email = Column(String, unique=True, nullable=True)
    name = Column(String, nullable=True)
    role = Column(String, nullable=False, server_default="member")
    active = Column(Boolean, nullable=False, server_default="true")

    created_at = timestamp_created()
    updated_at = timestamp_updated()