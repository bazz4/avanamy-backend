# src/avanamy/services/api_spec_service.py

from __future__ import annotations
import json
import logging
from uuid import uuid4
from typing import Optional

from sqlalchemy.orm import Session

from avanamy.repositories.api_spec_repository import ApiSpecRepository
from avanamy.services.s3 import upload_bytes
from avanamy.services.api_spec_parser import parse_api_spec
from avanamy.services.api_spec_normalizer import normalize_api_spec
from avanamy.services.documentation_service import generate_and_store_markdown_for_spec
from avanamy.metrics import (
    spec_upload_total,
    spec_parse_failures_total
)

logger = logging.getLogger(__name__)

def store_api_spec_file(
    db: Session,
    file_bytes: bytes,
    filename: str,
    content_type: Optional[str] = None,
    *,
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

    # ------------------------------------------------------------------------
    # 1. Parse → Normalize → JSON-serialize
    # ------------------------------------------------------------------------
    try:
        parsed_dict = parse_api_spec(filename, file_bytes)
        logger.info("Parsed spec successfully: filename=%s", filename)

        # Step 6: Normalize the parsed spec
        normalized_dict = normalize_api_spec(parsed_dict)
        logger.info("Normalized spec: endpoints=%d", len(normalized_dict.get("endpoints", [])))

        # Convert to JSON string so DB always stores text
        parsed_json = json.dumps(normalized_dict)
        logger.info("Serialized normalized spec to JSON: length=%d", len(parsed_json))

    except Exception:
        # graceful fallback
        parsed_json = None
        spec_parse_failures_total.inc()
        logger.exception("Failed to parse/normalize spec: filename=%s", filename)

    # ------------------------------------------------------------------------
    # 2. Upload to S3
    # ------------------------------------------------------------------------
    s3_key = f"api-specs/{uuid4()}-{filename}"
    _, s3_url = upload_bytes(s3_key, file_bytes, content_type=content_type)
    logger.info("Uploaded spec to S3: s3_key=%s", s3_key)
    # ------------------------------------------------------------------------
    # 3. Determine effective name
    # ------------------------------------------------------------------------
    effective_name = name or filename

    # ------------------------------------------------------------------------
    # 4. Store DB row
    # ------------------------------------------------------------------------
    repo = ApiSpecRepository()
    spec = repo.create(
        db,
        name=effective_name,
        version=version,
        description=description,
        original_file_s3_path=s3_url,
        parsed_schema=parsed_json,
    )

    logger.info("Created spec DB record: id=%s name=%s version=%s", spec.id, spec.name, spec.version)

    # ------------------------------------------------------------------------
    # 5. Generate documentation artifact (best-effort)
    # ------------------------------------------------------------------------
    try:
        logger.info("Generating documentation for spec_id=%s", spec.id)
        generate_and_store_markdown_for_spec(db, spec)
        logger.info("Finished documentation for spec_id=%s", spec.id)
    except Exception:
        # We never want docs generation to block spec ingestion
        logger.exception("Failed to generate documentation artifact for spec %s", spec.id)
    return spec
