# src/avanamy/repositories/api_spec_repository.py

from __future__ import annotations

import json
import logging
from uuid import UUID, uuid4

from sqlalchemy.orm import Session
from opentelemetry import trace, metrics

from avanamy.models.api_spec import ApiSpec

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)
meter = metrics.get_meter(__name__)

# Metrics – safe even without real exporter
api_spec_create_counter = meter.create_counter(
    "avanamy_api_spec_create_total",
    description="Count of initial ApiSpec records created for a product",
)
api_spec_update_counter = meter.create_counter(
    "avanamy_api_spec_update_total",
    description="Count of ApiSpec updates (new uploaded versions)",
)


class ApiSpecRepository:
    """
    Repository for raw persistence of ApiSpec.
    NO VERSION HISTORY OPERATIONS ARE PERFORMED HERE.
    Versioning is fully handled in api_spec_service.
    """

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------
    @staticmethod
    def _serialize_schema(parsed_schema: dict | str | None) -> str | None:
        if parsed_schema is None:
            return None
        if isinstance(parsed_schema, str):
            return parsed_schema
        return json.dumps(parsed_schema)

    # -------------------------------------------------------------------------
    # CREATE (low-level)
    # -------------------------------------------------------------------------
    @staticmethod
    def create(
        db: Session,
        *,
        tenant_id: str,
        name: str,
        version: str | None = None,
        description: str | None = None,
        original_file_s3_path: str | None = None,
        parsed_schema: dict | str | None = None,
        api_product_id: str | None = None,
        provider_id: str | None = None,  
    ) -> ApiSpec:

        schema_to_store = ApiSpecRepository._serialize_schema(parsed_schema)

        spec = ApiSpec(
            id=uuid4(),
            tenant_id=tenant_id,
            api_product_id=api_product_id,
            provider_id=provider_id,        
            name=name,
            version=version,
            description=description,
            original_file_s3_path=original_file_s3_path,
            parsed_schema=schema_to_store,
        )

        with tracer.start_as_current_span("db.create_api_spec") as span:
            span.set_attribute("tenant.id", tenant_id)
            span.set_attribute("spec.name", name)
            span.set_attribute("spec.version", version or "")
            span.set_attribute("spec.api_product_id", api_product_id or "")
            span.set_attribute("spec.provider_id", provider_id or "")   # ⭐ Optional trace

            try:
                db.add(spec)
                db.commit()
                db.refresh(spec)
                api_spec_create_counter.add(1, {"tenant.id": tenant_id})
            except Exception:
                logger.exception("DB create failed for ApiSpec name=%s", name)
                db.rollback()
                raise

        logger.info(
            "Created ApiSpec: id=%s tenant=%s product=%s provider=%s name=%s version=%s",
            spec.id,
            tenant_id,
            api_product_id,
            provider_id,
            name,
            version,
        )
        return spec

    # -------------------------------------------------------------------------
    # UPDATE (raw)
    # -------------------------------------------------------------------------
    @staticmethod
    def update(
        db: Session,
        *,
        spec: ApiSpec,
        parsed_schema: dict | str | None = None,
        description: str | None = None,
        original_file_s3_path: str | None = None,
        updated_by_user_id: str | None = None,
        version_label: str | None = None,
    ) -> ApiSpec:
        """
        Raw update for an existing ApiSpec.
        Does NOT create version history.
        """
        schema_to_store = ApiSpecRepository._serialize_schema(parsed_schema)

        if version_label is not None:
            spec.version = version_label
        if description is not None:
            spec.description = description
        if original_file_s3_path is not None:
            spec.original_file_s3_path = original_file_s3_path

        spec.parsed_schema = schema_to_store
        spec.updated_by_user_id = updated_by_user_id

        with tracer.start_as_current_span("db.update_api_spec") as span:
            span.set_attribute("tenant.id", spec.tenant_id)
            span.set_attribute("spec.id", str(spec.id))

            try:
                db.add(spec)
                db.commit()
                db.refresh(spec)
                api_spec_update_counter.add(1, {"tenant.id": spec.tenant_id})
            except Exception:
                logger.exception(
                    "Failed to update ApiSpec id=%s tenant=%s",
                    spec.id,
                    spec.tenant_id,
                )
                db.rollback()
                raise

        logger.info(
            "Updated ApiSpec id=%s tenant=%s to version=%s",
            spec.id,
            spec.tenant_id,
            spec.version,
        )
        return spec

    # -------------------------------------------------------------------------
    # READ HELPERS
    # -------------------------------------------------------------------------
    @staticmethod
    def get_by_id(db: Session, spec_id: UUID, tenant_id: str) -> ApiSpec | None:
        with tracer.start_as_current_span("db.get_api_spec_by_id") as span:
            span.set_attribute("tenant.id", tenant_id)
            span.set_attribute("spec.id", str(spec_id))

            return (
                db.query(ApiSpec)
                .filter(ApiSpec.id == spec_id, ApiSpec.tenant_id == tenant_id)
                .first()
            )

    @staticmethod
    def get_for_product(db: Session, tenant_id: str, api_product_id: str):
        return (
            db.query(ApiSpec)
            .filter(
                ApiSpec.tenant_id == tenant_id,
                ApiSpec.api_product_id == api_product_id,
            )
            .first()
        )

    @staticmethod
    def list_for_tenant(db: Session, tenant_id: str):
        with tracer.start_as_current_span("db.list_api_specs_for_tenant") as span:
            span.set_attribute("tenant.id", tenant_id)

            results = (
                db.query(ApiSpec)
                .filter(ApiSpec.tenant_id == tenant_id)
                .order_by(ApiSpec.created_at.desc())
                .all()
            )

        logger.debug(
            "Listed %d ApiSpecs for tenant=%s",
            len(results),
            tenant_id,
        )
        return results

    # -------------------------------------------------------------------------
    # DELETE
    # -------------------------------------------------------------------------
    @staticmethod
    def delete(db: Session, spec_id: UUID, tenant_id: str):
        with tracer.start_as_current_span("db.delete_api_spec") as span:
            span.set_attribute("tenant.id", tenant_id)
            span.set_attribute("spec.id", str(spec_id))

            spec = (
                db.query(ApiSpec)
                .filter(ApiSpec.id == spec_id, ApiSpec.tenant_id == tenant_id)
                .first()
            )

            if not spec:
                logger.warning(
                    "Attempted delete of missing ApiSpec id=%s tenant=%s",
                    spec_id,
                    tenant_id,
                )
                return False

            try:
                db.delete(spec)
                db.commit()
            except Exception:
                logger.exception(
                    "Failed to delete ApiSpec id=%s tenant=%s",
                    spec_id,
                    tenant_id,
                )
                db.rollback()
                raise

        logger.info("Deleted ApiSpec id=%s tenant=%s", spec_id, tenant_id)
        return True
