# src/avanamy/repositories/api_spec_repository.py

from sqlalchemy.orm import Session
from avanamy.models.api_spec import ApiSpec
import json
import logging
from opentelemetry import trace

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)

class ApiSpecRepository:

    @staticmethod
    def create(db: Session, *, tenant_id: str, name: str, version: str = None,
           description: str = None, original_file_s3_path: str = None,
           parsed_schema: dict = None) -> ApiSpec:

        # Ensure parsed_schema is stored as a JSON string for SQLite compatibility
        schema_to_store = None
        if parsed_schema is None:
            schema_to_store = None
        elif isinstance(parsed_schema, str):
            schema_to_store = parsed_schema
        else:
            # attempt to serialize dict/other to JSON string
            schema_to_store = json.dumps(parsed_schema)

        spec = ApiSpec(
            tenant_id=tenant_id,
            name=name,
            version=version,
            description=description,
            original_file_s3_path=original_file_s3_path,
            parsed_schema=schema_to_store,
        )

        with tracer.start_as_current_span("db.create_api_spec") as span:
            span.set_attribute("spec.name", name)
            try:
                db.add(spec)
                db.commit()
                db.refresh(spec)
            except Exception:
                logger.error("DB create failed for spec=%s", name)
                raise

        logger.info("Created ApiSpec: id=%s name=%s", spec.id, spec.name)
        return spec

    @staticmethod
    def get_by_id(db: Session, spec_id: int, tenant_id: str):
        return (
            db.query(ApiSpec)
            .filter(ApiSpec.id == spec_id, ApiSpec.tenant_id == tenant_id)
            .first()
        )


    @staticmethod
    def list_for_tenant(db: Session, tenant_id: str):
        return (
            db.query(ApiSpec)
            .filter(ApiSpec.tenant_id == tenant_id)
            .order_by(ApiSpec.created_at.desc())
            .all()
        )


    @staticmethod
    def delete(db: Session, spec_id: int, tenant_id: str):
        spec = (
            db.query(ApiSpec)
            .filter(ApiSpec.id == spec_id, ApiSpec.tenant_id == tenant_id)
            .first()
        )

