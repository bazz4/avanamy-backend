# src/avanamy/utils/filename_utils.py

import os
import re
import unicodedata
from uuid import uuid4
from pathlib import Path


def slugify_filename(name: str) -> str:
    """
    Convert any name into a safe S3 slug usable inside a key.
    """
    if not name:
        return "file"

    name = unicodedata.normalize("NFKD", name)
    name = name.encode("ascii", "ignore").decode("ascii")

    name = re.sub(r"[^a-zA-Z0-9._-]+", "-", name)
    name = name.strip("._-")
    name = name.lower()

    return name or "file"


def get_file_extension(filename: str) -> str:
    """
    Extract extension from a filename ("file.yaml" -> ".yaml").
    Returns empty string if not found.
    """
    _, ext = os.path.splitext(filename or "")
    return ext.lower()


def build_uploaded_spec_s3_key(
    tenant_id: str,
    spec_id: int,
    spec_name: str,
    original_filename: str,
) -> str:
    """
    Deterministic S3 key for uploaded API spec files under:
    tenants/<tenant_id>/specs/<spec_id>/<uuid>-<slug><ext>
    """
    slug = slugify_filename(spec_name)
    ext = get_file_extension(original_filename)
    unique = uuid4()

    return f"tenants/{tenant_id}/specs/{spec_id}/{unique}-{slug}{ext}"


def build_markdown_s3_key(tenant_id: str, spec_id: int, spec_name: str) -> str:
    slug = slugify_filename(spec_name)
    return f"tenants/{tenant_id}/docs/{spec_id}/{slug}.md"


def build_html_s3_key(tenant_id: str, spec_id: int, spec_name: str) -> str:
    slug = slugify_filename(spec_name)
    return f"tenants/{tenant_id}/docs/{spec_id}/{slug}.html"
