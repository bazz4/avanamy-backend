from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy import ForeignKey
from sqlalchemy import Column, Integer, String, Text, DateTime
from sqlalchemy.sql import func
from avanamy.db.database import Base

import sqlalchemy as sa

class ApiSpec(Base):
    __tablename__ = "api_specs"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=True)
    provider_id = Column(
        UUID(as_uuid=True),
        ForeignKey("providers.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    api_name = Column(String, nullable=True)
    name = Column(String, nullable=False)
    version = Column(String, nullable=True)
    description = Column(String, nullable=True)
    original_file_s3_path = Column(String, nullable=False)
    documentation_html_s3_path = Column(String, nullable=True)

    # IMPORTANT: store JSON *string* for SQLite compatibility
    parsed_schema = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    created_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    updated_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)

    __table_args__ = (
        # Prevent duplicate versions of the same API for the same provider + tenant
        sa.UniqueConstraint(
            "tenant_id",
            "provider_id",
            "api_name",
            "version",
            name="uq_api_specs_provider_api_version",
        ),
    )
