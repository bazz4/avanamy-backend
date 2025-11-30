# src/avanamy/services/api_spec_service.py

from __future__ import annotations
import json
from uuid import uuid4
from typing import Optional

from sqlalchemy.orm import Session

from avanamy.repositories.api_spec_repository import ApiSpecRepository
from avanamy.services.s3 import upload_bytes
from avanamy.services.api_spec_parser import parse_api_spec


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
    Uploads an API spec file to S3, parses it, and creates the DB record.

    This function accepts optional keyword overrides (`name`, `version`,
    `description`, `parsed_schema`) so callers (routes/tests) can pass them.
    """

    # 1. Try to parse the file (JSON/YAML/XML). If parsing fails, fall back
    # to any provided `parsed_schema` argument (already serialized) or None.
    parsed_json: Optional[str]
    try:
        parsed_dict = parse_api_spec(filename, file_bytes)
        parsed_json = json.dumps(parsed_dict)
    except Exception:
        parsed_dict = None
        # If caller provided parsed_schema as dict/string, ensure it's a JSON string
        if isinstance(parsed_schema, dict):
            parsed_json = json.dumps(parsed_schema)
        else:
            parsed_json = parsed_schema

    # 2. Generate an S3 key and upload bytes
    s3_key = f"api-specs/{uuid4()}-{filename}"
    _, s3_url = upload_bytes(s3_key, file_bytes, content_type=content_type)

    # 3. Determine effective name
    effective_name = name or filename

    # 4. Store DB row via repository (instantiate so tests that patch ApiSpecRepository
    # can control return values)
    repo = ApiSpecRepository()
    spec = repo.create(
        db,
        name=effective_name,
        version=version,
        description=description,
        original_file_s3_path=s3_url,
        parsed_schema=parsed_json,
    )

    return spec
