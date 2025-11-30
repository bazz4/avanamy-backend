# src/avanamy/services/documentation_service.py

from __future__ import annotations
from typing import Optional
import json

from sqlalchemy.orm import Session

from avanamy.models.api_spec import ApiSpec
from avanamy.repositories.documentation_artifact_repository import (
    DocumentationArtifactRepository,
)
from avanamy.services.s3 import upload_bytes
from avanamy.services.documentation_generator import (
    generate_markdown_from_normalized_spec,
)


ARTIFACT_TYPE_API_MARKDOWN = "api_markdown"


def generate_and_store_markdown_for_spec(
    db: Session,
    spec: ApiSpec,
) -> Optional[str]:
    """
    Generate Markdown documentation for a given ApiSpec and store it in S3.

    Returns the S3 path if successful, or None if there is no parsed_schema
    or if JSON decoding fails.
    """
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

    return key
