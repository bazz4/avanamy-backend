# src/avanamy/services/api_spec_service.py

from __future__ import annotations

import json
import logging
from uuid import uuid4
from typing import Optional

from sqlalchemy.orm import Session
from opentelemetry import trace

from avanamy.models.api_product import ApiProduct
from avanamy.models.api_spec import ApiSpec
from avanamy.models.provider import Provider
from avanamy.models.tenant import Tenant
from avanamy.repositories.api_spec_repository import ApiSpecRepository
from avanamy.repositories.version_history_repository import VersionHistoryRepository
from avanamy.services.s3 import (
    upload_bytes,
    copy_s3_object,
    delete_s3_object,
    generate_s3_url,
)
from avanamy.services.api_spec_parser import parse_api_spec
from avanamy.services.api_spec_normalizer import normalize_api_spec
from avanamy.services.documentation_service import (
    generate_and_store_markdown_for_spec,
    regenerate_all_docs_for_spec,
)
from avanamy.utils.filename_utils import slugify_filename, get_file_extension
from avanamy.utils.s3_paths import build_spec_upload_path
from avanamy.metrics import (
    spec_upload_total,
    spec_parse_failures_total,
)

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


async def store_api_spec_file(
    db: Session,
    file_bytes: bytes,
    filename: str,
    content_type: Optional[str] = None,
    *,
    tenant_id: str,
    api_product_id: str,          # NEW REQUIRED PARAM
    provider_id: Optional[str],   # NEW OPTIONAL PARAM
    name: Optional[str] = None,
    version: Optional[str] = None,
    description: Optional[str] = None,
    parsed_schema: Optional[str] = None,
):
    """
    Initial upload for a spec:
      1) Parse & normalize → JSON schema
      2) Temp S3 upload
      3) Create ApiSpec linked to api_product_id
      4) Create VersionHistory v1
      5) Move file to final S3 versioned path
      6) Generate docs for v1
    """
    logger.info("Starting spec upload: filename=%s", filename)
    spec_upload_total.inc()

    with tracer.start_as_current_span("service.store_api_spec") as span:
        span.set_attribute("filename", filename)
        span.set_attribute("file.size", len(file_bytes) if file_bytes else 0)

        existing_spec = ApiSpecRepository.get_by_product(
            db,
            tenant_id=tenant_id,
            provider_id=provider_id,
            api_product_id=api_product_id,
        )

        if existing_spec:
            logger.info(
                "Spec already exists for product %s; treating upload as update (spec_id=%s)",
                api_product_id,
                existing_spec.id,
            )
            return await update_api_spec_file(
                db,
                spec=existing_spec,
                file_bytes=file_bytes,
                filename=filename,
                content_type=content_type,
                tenant_id=tenant_id,
                description=description,
            )

        # --------------------------------------------------------------
        # 1. Parse → Normalize
        # --------------------------------------------------------------
        try:
            parsed_dict = parse_api_spec(filename, file_bytes)
            normalized_dict = normalize_api_spec(parsed_dict)
            parsed_json = json.dumps(normalized_dict)
        except Exception:
            logger.exception("Failed to parse/normalize spec %s", filename)
            spec_parse_failures_total.inc()
            parsed_json = None

        # --------------------------------------------------------------
        # 2. TEMP UPLOAD
        # --------------------------------------------------------------
        base_name = name or filename
        # Remove extension from base_name if present
        base_name_without_ext = base_name.rsplit('.', 1)[0] if '.' in base_name else base_name

        temp_key = (
            f"tenants/{tenant_id}/specs/pending/"
            f"{uuid4()}-{slugify_filename(base_name_without_ext)}{get_file_extension(filename)}"
        )
        _, temp_url = upload_bytes(temp_key, file_bytes, content_type=content_type)

        # --------------------------------------------------------------
        # 3a. Enforce one-spec-per-product invariant
        # --------------------------------------------------------------
        existing_spec = ApiSpecRepository.get_by_product(
            db,
            tenant_id=tenant_id,
            provider_id=provider_id,
            api_product_id=api_product_id,
        )

        if existing_spec:
            logger.info(
                "Spec already exists for product=%s; treating upload as update "
                "(existing spec_id=%s)",
                api_product_id,
                existing_spec.id,
            )

            # IMPORTANT: this is a policy decision
            # For now, reuse update flow
            return await update_api_spec_file(
                db,
                spec=existing_spec,
                file_bytes=file_bytes,
                filename=filename,
                content_type=content_type,
                tenant_id=tenant_id,
                description=description,
            )

        # --------------------------------------------------------------
        # 3. CREATE ApiSpec row (now requires api_product_id)
        # --------------------------------------------------------------
        effective_name = name or filename

        spec = ApiSpecRepository.create(
            db,
            tenant_id=tenant_id,
            api_product_id=api_product_id,     # IMPORTANT
            provider_id=provider_id,           # OPTIONAL
            name=effective_name,
            version=version,
            description=description,
            original_file_s3_path=temp_url,
            parsed_schema=parsed_json,
        )

        logger.info("Created ApiSpec id=%s for product=%s", spec.id, api_product_id)

        # --------------------------------------------------------------
        # 4. Resolve product + tenant
        # --------------------------------------------------------------
        product = db.query(ApiProduct).filter(ApiProduct.id == api_product_id).first()
        if not product:
            logger.error("ApiProduct %s not found", api_product_id)
            return None

        tenant = db.query(Tenant).filter(Tenant.id == product.tenant_id).first()
        if not tenant:
            logger.error("Tenant %s not found", product.tenant_id)
            return None

        # --------------------------------------------------------------
        # 5. Create VersionHistory v1
        # --------------------------------------------------------------
        vh = VersionHistoryRepository.create(
            db=db,
            api_spec_id=spec.id,
            changelog="Initial upload"
        )
        version_label = f"v{vh.version}"
        spec.version = version_label

        # --------------------------------------------------------------
        # 6. MOVE from temp → final versioned location
        # --------------------------------------------------------------
        provider = db.query(Provider).filter(Provider.id == product.provider_id).first()
        provider_slug = provider.slug

        base_spec_name = spec.name.rsplit('.', 1)[0] if '.' in spec.name else spec.name
        spec_slug = slugify_filename(base_spec_name)
        ext = get_file_extension(filename)

        final_key = build_spec_upload_path(
            tenant_slug=tenant.slug,
            provider_slug=provider_slug,
            product_slug=product.slug,
            version=version_label,
            spec_id=spec.id,
            spec_slug=spec_slug,
            ext=ext,
        )

        logger.info(
            "Moving spec file in S3: temp_key=%s final_key=%s tenant=%s product=%s spec_id=%s",
            temp_key,
            final_key,
            tenant.slug,
            product.slug,
            spec.id,
        )

        try:
            copy_s3_object(temp_key, final_key)
            delete_s3_object(temp_key)
            logger.info("Moved spec file in S3 successfully: final_key=%s", final_key)
        except Exception:
            logger.exception("Failed moving spec file in S3: temp_key=%s final_key=%s", temp_key, final_key)
            raise

        spec.original_file_s3_path = generate_s3_url(final_key)        
        db.commit()

        # --------------------------------------------------------------
        # 6.5. Store original spec artifact reference
        # --------------------------------------------------------------
        try:
            from avanamy.services.original_spec_artifact_service import store_original_spec_artifact
            
            store_original_spec_artifact(
                db,
                tenant_id=tenant.id,
                api_spec_id=spec.id,
                version_history_id=vh.id,
                s3_path=final_key,
            )
        except Exception:
            logger.exception("Failed storing original spec artifact for spec %s", spec.id)

        # --------------------------------------------------------------
        # 7. Generate normalized spec artifact
        # --------------------------------------------------------------
        try:
            from avanamy.services.normalized_spec_service import generate_and_store_normalized_spec
            
            generate_and_store_normalized_spec(
                db,
                tenant_slug=tenant.slug,
                provider_slug=provider_slug,
                product_slug=product.slug,
                version_label=version_label,
                spec_id=spec.id,
                spec_slug=spec_slug,
                parsed_spec=parsed_dict if parsed_dict else {},
                tenant_id=tenant.id,
            )
        except Exception:
            logger.exception("Failed generating normalized spec for spec %s", spec.id)

        # --------------------------------------------------------------
        # 8. Generate docs for v1
        # --------------------------------------------------------------
        try:
            await generate_and_store_markdown_for_spec(db, spec)
        except Exception:
            logger.exception("Failed generating docs for initial version of spec %s", spec.id)

        return spec

async def update_api_spec_file(
    db: Session,
    *,
    spec: ApiSpec,
    file_bytes: bytes,
    filename: str,
    content_type: Optional[str] = None,
    tenant_id: str,
    version: Optional[str] = None,
    description: Optional[str] = None,
):
    """
    Upload a *new* version of an existing ApiSpec.

    Steps:
      1) Parse & normalize updated spec
      2) Resolve product + tenant for slugs
      3) Create new VersionHistory row (version N+1)
      4) Store raw spec file under that version in S3
      5) Update spec row (version label, parsed_schema, s3_path, description)
      6) Regenerate docs for that same version (overwrite artifacts)
    """
    logger.info(
        "Starting spec update: spec_id=%s filename=%s",
        getattr(spec, "id", None),
        filename,
    )
    spec_upload_total.inc()

    with tracer.start_as_current_span("service.update_api_spec") as span:
        span.set_attribute("spec.id", getattr(spec, "id", None))
        span.set_attribute("tenant.id", tenant_id)
        span.set_attribute("filename", filename)
        span.set_attribute("file.size", len(file_bytes) if file_bytes is not None else 0)

        # --------------------------------------------------------------------
        # 1. Parse → Normalize → JSON-serialize
        # --------------------------------------------------------------------
        parsed_json = None
        try:
            parsed_dict = parse_api_spec(filename, file_bytes)
            logger.info(
                "Parsed spec successfully for update: spec_id=%s filename=%s",
                getattr(spec, "id", None),
                filename,
            )

            with tracer.start_as_current_span("service.normalize_spec") as normalize_span:
                normalized_dict = normalize_api_spec(parsed_dict)
                endpoints_count = 0
                if isinstance(normalized_dict, dict):
                    endpoints = normalized_dict.get("paths", {})
                    endpoints_count = len(endpoints) if isinstance(endpoints, dict) else 0
                normalize_span.set_attribute("endpoints.count", endpoints_count)

            parsed_json = json.dumps(normalized_dict)
            logger.debug(
                "Serialized normalized spec to JSON for update: length=%d",
                len(parsed_json),
            )

        except Exception:
            spec_parse_failures_total.inc()
            logger.exception(
                "Failed to parse/normalize spec during update: spec_id=%s filename=%s",
                getattr(spec, "id", None),
                filename,
            )

        # --------------------------------------------------------------------
        # 2. Resolve ApiProduct + Tenant (for slugs)
        # --------------------------------------------------------------------
        product = db.query(ApiProduct).filter(ApiProduct.id == spec.api_product_id).first()
        if not product:
            logger.error("ApiProduct not found for spec_id=%s", spec.id)
            raise ValueError("ApiProduct not found")

        tenant = db.query(Tenant).filter(Tenant.id == product.tenant_id).first()
        if not tenant:
            logger.error("Tenant not found for product_id=%s", product.id)
            raise ValueError("Tenant not found")

        # --------------------------------------------------------------------
        # 3. Create new VersionHistory row and compute label
        # --------------------------------------------------------------------
        vh = VersionHistoryRepository.create(
            db=db,
            api_spec_id=spec.id,
            diff=None,
            changelog="Uploaded new version",
        )
        version_label = f"v{vh.version}"
        spec.version = version_label

        # --------------------------------------------------------------------
        # 4. Upload new spec file to S3 under THIS version
        # --------------------------------------------------------------------
        provider = db.query(Provider).filter(Provider.id == product.provider_id).first()
        if not provider:
            logger.error("Provider not found for provider_id=%s", product.provider_id)
            return None

        provider_slug = provider.slug

        base_spec_name = spec.name.rsplit('.', 1)[0] if '.' in spec.name else spec.name
        spec_slug = slugify_filename(base_spec_name)

        ext = get_file_extension(filename)

        final_key = build_spec_upload_path(
            tenant_slug=tenant.slug,
            provider_slug=provider_slug,
            product_slug=product.slug,
            version=version_label,
            spec_id=spec.id,
            spec_slug=spec_slug,
            ext=ext,
        )

        with tracer.start_as_current_span("service.s3_upload_spec_update") as s3_span:
            s3_span.set_attribute("tenant.id", tenant_id)
            s3_span.set_attribute("spec.id", spec.id)
            s3_span.set_attribute("s3.key", final_key)
            s3_span.set_attribute("file.size", len(file_bytes))
            upload_bytes(final_key, file_bytes, content_type=content_type)

        spec.original_file_s3_path = generate_s3_url(final_key)

        # --------------------------------------------------------------------
        # 4.5. Store original spec artifact reference
        # --------------------------------------------------------------------
        try:
            from avanamy.services.original_spec_artifact_service import store_original_spec_artifact
            
            store_original_spec_artifact(
                db,
                tenant_id=tenant.id,
                api_spec_id=spec.id,
                version_history_id=vh.id,
                s3_path=final_key,
            )
        except Exception:
            logger.exception("Failed storing original spec artifact for spec %s", spec.id)


        # --------------------------------------------------------------------
        # 5. Update spec fields
        # --------------------------------------------------------------------
        if description is not None:
            spec.description = description
        if parsed_json is not None:
            spec.parsed_schema = parsed_json

        db.commit()
        db.refresh(spec)

        # --------------------------------------------------------------------
        # 5b. Generate normalized spec artifact
        # --------------------------------------------------------------------
        try:
            from avanamy.services.normalized_spec_service import generate_and_store_normalized_spec
            
            generate_and_store_normalized_spec(
                db,
                tenant_slug=tenant.slug,
                provider_slug=provider_slug,
                product_slug=product.slug,
                version_label=version_label,
                spec_id=spec.id,
                spec_slug=spec_slug,
                parsed_spec=parsed_dict if parsed_dict else {},
                tenant_id=tenant.id,
            )
        except Exception:
            logger.exception("Failed generating normalized spec for spec %s", spec.id)

        # --------------------------------------------------------------------
        # 5c. Compute and store diff
        # --------------------------------------------------------------------
        try:
            from avanamy.services.version_diff_service import compute_and_store_diff
            from avanamy.services.spec_normalizer import normalize_openapi_spec
            
            # Generate normalized spec for diffing
            current_normalized = normalize_openapi_spec(parsed_dict if parsed_dict else {})
            
            compute_and_store_diff(
                db,
                spec_id=spec.id,
                tenant_id=tenant.id,
                current_version=vh.version,
                new_normalized_spec=current_normalized,
            )
        except Exception:
            logger.exception("Failed computing diff for spec %s version %s", spec.id, vh.version)


        # --------------------------------------------------------------------
        # 6. Regenerate documentation (best-effort) for THIS version
        # --------------------------------------------------------------------
        try:
            logger.info("Regenerating documentation for updated spec_id=%s", spec.id)
            with tracer.start_as_current_span("service.generate_docs_update") as docs_span:
                docs_span.set_attribute("spec.id", spec.id)
                # Use the same helper; it will use the current VersionHistory version
                await regenerate_all_docs_for_spec(db, spec)
            logger.info("Finished documentation regeneration for spec_id=%s", spec.id)
        except Exception:
            logger.exception(
                "Failed to regenerate documentation for updated spec %s",
                spec.id,
            )

        return spec