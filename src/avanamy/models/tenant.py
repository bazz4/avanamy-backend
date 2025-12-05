import uuid

from sqlalchemy import Column, String, DateTime, func
from sqlalchemy.dialects.postgresql import UUID

from avanamy.db.database import Base


class Tenant(Base):
    __tablename__ = "tenants"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)

    # URL-safe unique tenant slug, auto-generated from name
    slug = Column(String, unique=True, nullable=False)

    # active / suspended / deleted
    status = Column(String, nullable=False, default="active")

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
