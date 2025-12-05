from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy import ForeignKey
from sqlalchemy import Column, Integer, String, Text, DateTime
from sqlalchemy.sql import func
from avanamy.db.database import Base

class ApiSpec(Base):
    __tablename__ = "api_specs"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=True)
    name = Column(String, nullable=False)
    version = Column(String, nullable=True)
    description = Column(String, nullable=True)
    original_file_s3_path = Column(String, nullable=False)
    documentation_html_s3_path = Column(String, nullable=True)

    # IMPORTANT: store JSON *string* for SQLite compatibility
    parsed_schema = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
