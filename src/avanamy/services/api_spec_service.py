from __future__ import annotations

from typing import Optional, Dict, Any
from uuid import uuid4

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
):
    """
    Uploads an API spec file to S3, parses it, and creates the DB record.
    """

    # 1. Parse the file (JSON, YAML, XML, fallback)
    parsed_schema = parse_api_spec(filename, file_bytes)

    # 2. Generate an S3 key
    s3_key = f"api-specs/{uuid4()}-{filename}"

    # 3. Upload bytes to S3
    _, s3_url = upload_bytes(
        key=s3_key,
        data=file_bytes,
        content_type=content_type,
    )

    # 4. Derive default name
    effective_name = name or filename

    # 5. Create DB entry
    spec = ApiSpecRepository.create(
        db,
        name=effective_name,
        version=version,
        description=description,
        original_file_s3_path=s3_url,
        parsed_schema=parsed_schema,
    )

    return spec
