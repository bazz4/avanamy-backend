from sqlalchemy import Column, String, Text
from sqlalchemy.orm import relationship
from avanamy.db.database import Base
from avanamy.models.base_model import uuid_pk, uuid_fk, timestamp_created, timestamp_updated
import sqlalchemy as sa

class ApiSpec(Base):
    __tablename__ = "api_specs"

    id = uuid_pk()
    tenant_id = uuid_fk("tenants", nullable=True)
    provider_id = uuid_fk("providers", nullable=True, ondelete="SET NULL")
    api_product_id = uuid_fk("api_products", nullable=True, ondelete="SET NULL")
    
    api_name = Column(String, nullable=True)
    name = Column(String, nullable=False)
    version = Column(String, nullable=True)
    description = Column(String, nullable=True)
    original_file_s3_path = Column(String, nullable=False)
    documentation_html_s3_path = Column(String, nullable=True)
    parsed_schema = Column(Text, nullable=True)

    created_at = timestamp_created()
    updated_at = timestamp_updated()
    created_by_user_id = uuid_fk("users", nullable=True)
    updated_by_user_id = uuid_fk("users", nullable=True)

    __table_args__ = (
        sa.UniqueConstraint(
            "tenant_id",
            "provider_id",
            "api_name",
            "version",
            name="uq_api_specs_provider_api_version",
        ),
    )

    watched_apis = relationship("WatchedAPI", back_populates="api_spec")