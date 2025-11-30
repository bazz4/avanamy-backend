# src/avanamy/services/documentation_service.py

from __future__ import annotations
from typing import Optional
import json
import logging 
from sqlalchemy.orm import Session

from avanamy.models.api_spec import ApiSpec
from avanamy.repositories.documentation_artifact_repository import (
    DocumentationArtifactRepository,
)
from avanamy.services.s3 import upload_bytes
from avanamy.services.documentation_generator import (
    generate_markdown_from_normalized_spec,
)
from avanamy.metrics import markdown_generation_total
from opentelemetry import trace

ARTIFACT_TYPE_API_MARKDOWN = "api_markdown"

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)

def generate_and_store_markdown_for_spec(
    db: Session,
    spec: ApiSpec,
) -> Optional[str]:
    """
    Generate Markdown documentation for a given ApiSpec and store it in S3.

    Returns the S3 path if successful, or None if there is no parsed_schema
    or if JSON decoding fails.
    """
    logger.info("Starting markdown generation: spec_id=%s", spec.id)

    with tracer.start_as_current_span("generate_docs_for_spec") as span:
        span.set_attribute("spec.id", str(spec.id))
        span.set_attribute("spec.name", str(spec.name or ""))
        span.set_attribute("spec.version", str(spec.version or ""))

        if not spec.parsed_schema:
            logger.warning(
                "Spec %s has no parsed_schema — skipping markdown generation.",
                spec.id,
            )
            span.set_attribute("docs.skipped_reason", "missing_parsed_schema")
            return None

    if not spec.parsed_schema:
        # Nothing to generate docs from
        return None

    try:
        raw = spec.parsed_schema

        if raw is None:
            return None

        if isinstance(raw, dict):
            schema = raw
        else:
            schema = json.loads(raw)
    except json.JSONDecodeError:
        return None

    markdown = generate_markdown_from_normalized_spec(schema)
    key = f"docs/{spec.id}/api.md"

    _, s3_url = upload_bytes(key, markdown.encode("utf-8"), "text/markdown")


    repo = DocumentationArtifactRepository()
    repo.create(
        db,
        api_spec_id=spec.id,
        artifact_type=ARTIFACT_TYPE_API_MARKDOWN,
        s3_path=key,  # store S3 key; or s3_url if you prefer
    )
    markdown_generation_total.inc()
    return key
