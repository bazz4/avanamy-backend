# src/avanamy/models/user.py

from sqlalchemy import Column, String, DateTime, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from avanamy.db.database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True)

    # Optional tenant (for future multi-tenant admin users)
    tenant_id = Column(UUID(as_uuid=True), nullable=True)

    # Identity fields
    email = Column(String, unique=True, nullable=True)
    name = Column(String, nullable=True)

    # Simple role
    role = Column(String, nullable=False, server_default="member")

    # Soft-delete flag
    active = Column(Boolean, nullable=False, server_default="true")

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now()
    )
