# src/avanamy/repositories/api_spec_repository.py

from __future__ import annotations

import json
import logging
from uuid import UUID, uuid4

from sqlalchemy.orm import Session
from opentelemetry import trace, metrics

from avanamy.models.api_spec import ApiSpec
from avanamy.repositories.version_history_repository import VersionHistoryRepository

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)
meter = metrics.get_meter(__name__)

# Simple metrics – safe even if you don't have a real exporter wired
api_spec_create_counter = meter.create_counter(
    "avanamy_api_spec_create_total",
    description="Count of initial ApiSpec records created for a product",
)
api_spec_update_counter = meter.create_counter(
    "avanamy_api_spec_update_total",
    description="Count of ApiSpec updates (new uploaded versions)",
)
api_spec_version_counter = meter.create_counter(
    "avanamy_api_spec_version_total",
    description="Count of VersionHistory entries created",
)


class ApiSpecRepository:
    """
    ApiSpec is the *current* spec for an api_product.
    VersionHistory stores the versioned history for that spec.
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
    # Existing "raw" create (still used in some places)
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
    ) -> ApiSpec:
        """
        Low-level create. Prefer the product-aware helpers below for new code.
        """
        schema_to_store = ApiSpecRepository._serialize_schema(parsed_schema)

        spec = ApiSpec(
            id=uuid4(),  # if your model is UUID primary key
            tenant_id=tenant_id,
            api_product_id=api_product_id,
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
            "Created ApiSpec: id=%s tenant=%s product=%s name=%s version=%s",
            spec.id,
            tenant_id,
            api_product_id,
            name,
            version,
        )
        return spec

    # -------------------------------------------------------------------------
    # NEW: product-aware initial create
    # -------------------------------------------------------------------------
    @staticmethod
    def create_initial_for_product(
        db: Session,
        *,
        tenant_id: str,
        api_product_id: str,
        name: str,
        version_label: str,
        description: str | None = None,
        original_file_s3_path: str | None = None,
        parsed_schema: dict | str | None = None,
        changelog: str | None = None,
        created_by_user_id: str | None = None,
    ) -> ApiSpec:
        """
        Create the *first* ApiSpec for a given api_product_id and record v1 in VersionHistory.
        Fails if a spec already exists for this product+tenant.
        """
        with tracer.start_as_current_span("db.create_initial_api_spec_for_product") as span:
            span.set_attribute("tenant.id", tenant_id)
            span.set_attribute("api_product.id", api_product_id)
            span.set_attribute("version.label", version_label)

            existing = (
                db.query(ApiSpec)
                .filter(
                    ApiSpec.tenant_id == tenant_id,
                    ApiSpec.api_product_id == api_product_id,
                )
                .one_or_none()
            )

            if existing:
                logger.error(
                    "ApiSpec already exists for tenant=%s product=%s; refusing initial create",
                    tenant_id,
                    api_product_id,
                )
                raise ValueError("ApiSpec already exists for this product; use update_for_product")

            schema_to_store = ApiSpecRepository._serialize_schema(parsed_schema)

            spec = ApiSpec(
                id=uuid4(),  # if UUID pk
                tenant_id=tenant_id,
                api_product_id=api_product_id,
                name=name,
                version=version_label,
                description=description,
                original_file_s3_path=original_file_s3_path,
                parsed_schema=schema_to_store,
                created_by_user_id=created_by_user_id,
            )

            try:
                db.add(spec)
                db.flush()  # get spec.id for VersionHistory

                VersionHistoryRepository.create(
                    db,
                    tenant_id=tenant_id,
                    api_spec_id=spec.id,
                    version_label=version_label,
                    changelog=changelog or "Initial upload",
                )
                api_spec_version_counter.add(1, {"tenant.id": tenant_id})

                db.commit()
                db.refresh(spec)
                api_spec_create_counter.add(1, {"tenant.id": tenant_id})
            except Exception:
                logger.exception(
                    "Failed to create initial ApiSpec + VersionHistory for tenant=%s product=%s",
                    tenant_id,
                    api_product_id,
                )
                db.rollback()
                raise

        logger.info(
            "Created initial ApiSpec id=%s for tenant=%s product=%s version=%s",
            spec.id,
            tenant_id,
            api_product_id,
            version_label,
        )
        return spec

    # -------------------------------------------------------------------------
    # NEW: update existing spec for a product (new uploaded version)
    # -------------------------------------------------------------------------
    @staticmethod
    def update_for_product(
        db: Session,
        *,
        tenant_id: str,
        api_product_id: str,
        new_version_label: str,
        parsed_schema: dict | str | None,
        description: str | None = None,
        original_file_s3_path: str | None = None,
        changelog: str | None = None,
        updated_by_user_id: str | None = None,
    ) -> ApiSpec:
        """
        Replace the existing ApiSpec for a product with a new version, and append VersionHistory.

        Flow:
        - Load current spec (must exist)
        - Append VersionHistory row for *new* version
        - Overwrite ApiSpec fields to reflect latest version
        """
        with tracer.start_as_current_span("db.update_api_spec_for_product") as span:
            span.set_attribute("tenant.id", tenant_id)
            span.set_attribute("api_product.id", api_product_id)
            span.set_attribute("version.label.new", new_version_label)

            spec = (
                db.query(ApiSpec)
                .filter(
                    ApiSpec.tenant_id == tenant_id,
                    ApiSpec.api_product_id == api_product_id,
                )
                .one_or_none()
            )

            if spec is None:
                logger.error(
                    "No ApiSpec found for tenant=%s product=%s when attempting update",
                    tenant_id,
                    api_product_id,
                )
                raise ValueError("No ApiSpec exists for this product; call create_initial_for_product first")

            # Record new version row
            VersionHistoryRepository.create(
                db,
                tenant_id=tenant_id,
                api_spec_id=spec.id,
                version_label=new_version_label,
                changelog=changelog or "Updated spec uploaded",
            )
            api_spec_version_counter.add(1, {"tenant.id": tenant_id})

            # Overwrite current spec fields
            schema_to_store = ApiSpecRepository._serialize_schema(parsed_schema)

            spec.version = new_version_label
            if description is not None:
                spec.description = description
            if original_file_s3_path is not None:
                spec.original_file_s3_path = original_file_s3_path
            spec.parsed_schema = schema_to_store
            spec.updated_by_user_id = updated_by_user_id

            try:
                db.add(spec)
                db.commit()
                db.refresh(spec)
                api_spec_update_counter.add(1, {"tenant.id": tenant_id})
            except Exception:
                logger.exception(
                    "Failed to update ApiSpec for tenant=%s product=%s",
                    tenant_id,
                    api_product_id,
                )
                db.rollback()
                raise

        logger.info(
            "Updated ApiSpec id=%s for tenant=%s product=%s to version=%s",
            spec.id,
            tenant_id,
            api_product_id,
            new_version_label,
        )
        return spec

    # -------------------------------------------------------------------------
    # Read helpers (mostly what you already had)
    # -------------------------------------------------------------------------
    @staticmethod
    def get_by_id(db: Session, spec_id: UUID, tenant_id: str) -> ApiSpec | None:
        with tracer.start_as_current_span("db.get_api_spec_by_id") as span:
            span.set_attribute("tenant.id", tenant_id)
            span.set_attribute("spec.id", spec_id)

            result = (
                db.query(ApiSpec)
                .filter(ApiSpec.id == spec_id, ApiSpec.tenant_id == tenant_id)
                .first()
            )

        return result

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
    def create_initial_for_product(
        db: Session,
        *,
        tenant_id: str,
        api_product_id: str,
        name: str,
        description: str | None,
        version_label: str,
        parsed_schema: dict,
        created_by_user_id: str,
        original_file_s3_path: str,
        changelog: str,
    ):
        spec = ApiSpec(
            tenant_id=tenant_id,
            api_product_id=api_product_id,
            name=name,
            description=description,
            parsed_schema=json.dumps(parsed_schema),
            original_file_s3_path=original_file_s3_path,
            created_by_user_id=created_by_user_id,
            version=version_label,
        )

        db.add(spec)
        db.commit()
        db.refresh(spec)

        VersionHistoryRepository.create(
            db=db,
            tenant_id=tenant_id,
            api_spec_id=spec.id,
            version_label=version_label,
            changelog=changelog,
        )

        return spec

    @staticmethod
    def update_for_product(
        db: Session,
        *,
        tenant_id: str,
        api_product_id: str,
        parsed_schema: dict,
        new_version_label: str,
        description: str | None,
        updated_by_user_id: str,
        original_file_s3_path: str,
        changelog: str,
    ):
        spec = (
            db.query(ApiSpec)
            .filter(
                ApiSpec.tenant_id == tenant_id,
                ApiSpec.api_product_id == api_product_id,
            )
            .first()
        )

        spec.parsed_schema = json.dumps(parsed_schema)
        spec.description = description
        spec.original_file_s3_path = original_file_s3_path
        spec.version = new_version_label
        spec.updated_by_user_id = updated_by_user_id

        db.commit()
        db.refresh(spec)

        VersionHistoryRepository.create(
            db=db,
            tenant_id=tenant_id,
            api_spec_id=spec.id,
            version_label=new_version_label,
            changelog=changelog,
        )

        return spec

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

    @staticmethod
    def delete(db: Session, spec_id: UUID, tenant_id: str):
        with tracer.start_as_current_span("db.delete_api_spec") as span:
            span.set_attribute("tenant.id", tenant_id)
            span.set_attribute("spec.id", spec_id)

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
