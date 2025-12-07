# src/avanamy/services/api_spec_service.py

from __future__ import annotations
import json
import logging
from uuid import uuid4
from typing import Optional

from sqlalchemy.orm import Session

from avanamy.models.api_spec import ApiSpec
from avanamy.repositories.api_spec_repository import ApiSpecRepository
from avanamy.repositories.version_history_repository import VersionHistoryRepository
from avanamy.services.s3 import upload_bytes, upload_bytes, copy_s3_object, delete_s3_object, generate_s3_url
from avanamy.services.api_spec_parser import parse_api_spec
from avanamy.services.api_spec_normalizer import normalize_api_spec
from avanamy.services.documentation_service import generate_and_store_markdown_for_spec, regenerate_all_docs_for_spec
from avanamy.utils.filename_utils import build_uploaded_spec_s3_key, slugify_filename, get_file_extension 
from avanamy.metrics import (
    spec_upload_total,
    spec_parse_failures_total
)

logger = logging.getLogger(__name__)
from opentelemetry import trace

tracer = trace.get_tracer(__name__)

def store_api_spec_file(
    db: Session,
    file_bytes: bytes,
    filename: str,
    content_type: Optional[str] = None,
    *,
    tenant_id: str,
    name: Optional[str] = None,
    version: Optional[str] = None,
    description: Optional[str] = None,
    parsed_schema: Optional[str] = None,
):
    """
    Upload an API spec file to S3, parse it, normalize it, and create the DB record.
    """
    logger.info("Starting spec upload: filename=%s", filename)
    spec_upload_total.inc()

    with tracer.start_as_current_span("service.store_api_spec") as span:
        span.set_attribute("filename", filename)
        span.set_attribute("file.size", len(file_bytes) if file_bytes is not None else 0)

        # --------------------------------------------------------------------
        # 1. Parse → Normalize → JSON-serialize
        # --------------------------------------------------------------------
        try:
            parsed_dict = parse_api_spec(filename, file_bytes)
            logger.info("Parsed spec successfully: filename=%s", filename)

            with tracer.start_as_current_span("service.normalize_spec") as normalize_span:
                normalized_dict = normalize_api_spec(parsed_dict)
                endpoints_count = len(normalized_dict.get("endpoints", [])) if normalized_dict else 0
                normalize_span.set_attribute("endpoints.count", endpoints_count)
            logger.info("Normalized spec: endpoints=%d", endpoints_count)

            parsed_json = json.dumps(normalized_dict)
            logger.debug("Serialized normalized spec to JSON: length=%d", len(parsed_json))

        except Exception:
            parsed_json = None
            spec_parse_failures_total.inc()
            logger.exception("Failed to parse/normalize spec: filename=%s", filename)

        # --------------------------------------------------------------------
        # 2. TEMP UPLOAD (because spec_id does not exist yet)
        # --------------------------------------------------------------------
        temp_key = (
            f"tenants/{tenant_id}/specs/pending/"
            f"{uuid4()}-{slugify_filename(name or filename)}{get_file_extension(filename)}"
        )

        with tracer.start_as_current_span("service.s3_upload_temp") as s3_span:
            s3_span.set_attribute("tenant.id", tenant_id)
            s3_span.set_attribute("s3.key", temp_key)
            s3_span.set_attribute("file.size", len(file_bytes))
            _, temp_url = upload_bytes(temp_key, file_bytes, content_type=content_type)

        logger.info("Uploaded temp spec to S3: temp_key=%s", temp_key)

        # --------------------------------------------------------------------
        # 3. CREATE SPEC DB RECORD
        # --------------------------------------------------------------------
        effective_name = name or filename

        # --------------------------------------------------------------------
        # 4. Store DB row
        # --------------------------------------------------------------------
        repo = ApiSpecRepository()
        with tracer.start_as_current_span("db.create_api_spec") as db_span:
            db_span.set_attribute("tenant.id", tenant_id)
            db_span.set_attribute("spec.name", effective_name)
            spec = repo.create(
                db,
                tenant_id=tenant_id,
                name=effective_name,
                version=version,
                description=description,
                original_file_s3_path=temp_url,
                parsed_schema=parsed_json,
            )

        # Determine next version label
        version_label = VersionHistoryRepository.next_version_for_spec(db, spec.id)

        # Create version history entry
        VersionHistoryRepository.create(
            db=db,
            api_spec_id=spec.id,
            diff=None,
            changelog="Initial upload",
        )

        logger.info("Created spec DB record: id=%s", spec.id)

        # --------------------------------------------------------------------
        # 4. MOVE S3 OBJECT INTO FINAL LOCATION
        # --------------------------------------------------------------------
        final_key = build_uploaded_spec_s3_key(
            tenant_id=str(tenant_id),
            spec_id=spec.id,
            spec_name=effective_name,
            original_filename=filename,
        )

        copy_s3_object(temp_key, final_key)
        delete_s3_object(temp_key)

        spec.original_file_s3_path = generate_s3_url(final_key)
        db.commit()

        # --------------------------------------------------------------------
        # 5. Generate documentation artifact (best-effort)
        # --------------------------------------------------------------------
        try:
            logger.info("Generating documentation for spec_id=%s", spec.id)
            with tracer.start_as_current_span("service.generate_docs") as docs_span:
                    docs_span.set_attribute("spec.id", str(spec.id))
                    generate_and_store_markdown_for_spec(db, spec)
            logger.info("Finished documentation for spec_id=%s", spec.id)
        except Exception:
            logger.exception("Failed to generate documentation artifact for spec %s", spec.id)

        return spec

def update_api_spec_file(
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
    Update an existing ApiSpec with a new uploaded file:
      - parse + normalize the new spec
      - store raw file in S3
      - update spec fields (version, description, parsed_schema, s3 path)
      - regenerate markdown + HTML docs

    This mirrors store_api_spec_file but operates on an existing spec row.
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
        # 2. Upload new original file to S3 (final location)
        # --------------------------------------------------------------------
        final_key = build_uploaded_spec_s3_key(
            tenant_id=str(tenant_id),
            spec_id=spec.id,
            spec_name=spec.name or filename,
            original_filename=filename,
        )

        with tracer.start_as_current_span("service.s3_upload_spec_update") as s3_span:
            s3_span.set_attribute("tenant.id", tenant_id)
            s3_span.set_attribute("spec.id", spec.id)
            s3_span.set_attribute("s3.key", final_key)
            s3_span.set_attribute("file.size", len(file_bytes))
            upload_bytes(final_key, file_bytes, content_type=content_type)

        spec.original_file_s3_path = generate_s3_url(final_key)

        # --------------------------------------------------------------------
        # 3. Update spec fields
        # --------------------------------------------------------------------
        if version is not None:
            spec.version = version
        if description is not None:
            spec.description = description
        if parsed_json is not None:
            spec.parsed_schema = parsed_json

        db.commit()
        db.refresh(spec)

       # --------------------------------------------------------------------
        # 4. Create version history row
        # --------------------------------------------------------------------
        try:
            version_label = VersionHistoryRepository.next_version_for_spec(db, spec.id)

            VersionHistoryRepository.create(
                db=db,
                api_spec_id=spec.id,
                diff=None,  # we can wire in real diffs later
                changelog=f"Uploaded {version_label}",
            )

            logger.info(
                "Recorded version history for spec_id=%s label=%s",
                spec.id,
                version_label,
            )
        except Exception:
            logger.exception(
                "Failed to record version history for spec %s",
                spec.id,
            )
        # --------------------------------------------------------------------
        # 5. Regenerate documentation (best-effort)
        # --------------------------------------------------------------------
        try:
            logger.info("Regenerating documentation for updated spec_id=%s", spec.id)
            with tracer.start_as_current_span("service.generate_docs_update") as docs_span:
                docs_span.set_attribute("spec.id", spec.id)
                regenerate_all_docs_for_spec(db, spec)
            logger.info("Finished documentation regeneration for spec_id=%s", spec.id)
        except Exception:
            logger.exception(
                "Failed to regenerate documentation for updated spec %s",
                spec.id,
            )

        return spec