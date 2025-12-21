# src/avanamy/models/provider.py

from sqlalchemy import (
    Column,
    String,
    DateTime,
    ForeignKey,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from avanamy.db.database import Base


class Provider(Base):
    """
    Provider = upstream platform whose API a tenant integrates with.
    Examples: DoorDash, Uber Eats, Shopify, Toast, etc.

    - tenant_id NULL  => "global" provider definition (can be shared)
    - tenant_id NOT NULL => tenant-specific provider (override/custom)
    """

    __tablename__ = "providers"

    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True)

    # Optional tenant scope: NULL means global, otherwise per-tenant
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=True)

    # Human-friendly name: "DoorDash", "Uber Eats", "Shopify"
    name = Column(String, nullable=False)

    # Slug used in URLs, S3 paths, etc. (e.g. "doordash", "uber-eats")
    slug = Column(String, nullable=False)

    # Simple lifecycle flag (for now just "active"/"inactive")
    status = Column(String, nullable=False, server_default="active")

    # Audit timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Who created / last updated this provider (optional)
    created_by_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=True,
    )
    updated_by_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=True,
    )

    __table_args__ = (
        # Ensure uniqueness of slug within a tenant, but allow global + per-tenant
        # NULL tenant_id + slug is allowed once, and each tenant can have that slug too.
        UniqueConstraint(
            "tenant_id",
            "slug",
            name="uq_providers_tenant_slug",
        ),
    )

    # Relationships
    watched_apis = relationship("WatchedAPI", back_populates="provider")
