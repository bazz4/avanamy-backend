# src/avanamy/utils/s3_paths.py

from __future__ import annotations

from uuid import UUID
from avanamy.utils.filename_utils import slugify_filename, get_file_extension


def build_tenant_root(tenant_slug: str) -> str:
    return f"tenants/{tenant_slug}"


def build_product_root(tenant_slug: str, product_slug: str) -> str:
    tenant_root = build_tenant_root(tenant_slug)
    return f"{tenant_root}/api_products/{product_slug}"


def build_version_root(tenant_slug: str, product_slug: str, version: str) -> str:
    product_root = build_product_root(tenant_slug, product_slug)
    return f"{product_root}/versions/{version}"


# ---------------------------------------------------------------------------
# Specs
# ---------------------------------------------------------------------------

def build_spec_upload_path(
    tenant_slug: str,
    product_slug: str,
    version: str,
    spec_id: int | UUID,
    filename: str,
) -> str:
    """
    S3 key for the uploaded spec file:
    tenants/{tenant_slug}/api_products/{product_slug}/versions/{version}/specs/{spec_id}/{filename}
    """
    version_root = build_version_root(tenant_slug, product_slug, version)

    # keep original filename but slugify the "name" portion
    base, ext = filename.rsplit(".", 1) if "." in filename else (filename, "")
    safe_name = slugify_filename(base)
    safe_ext = f".{ext}" if ext else ""

    return f"{version_root}/specs/{spec_id}/{safe_name}{safe_ext}"


# ---------------------------------------------------------------------------
# Docs (Markdown + HTML)
# ---------------------------------------------------------------------------

def build_docs_markdown_path(
    tenant_slug: str,
    product_slug: str,
    version: str,
) -> str:
    """
    S3 key for markdown docs:
    tenants/{tenant_slug}/api_products/{product_slug}/versions/{version}/docs/markdown/index.md
    """
    version_root = build_version_root(tenant_slug, product_slug, version)
    return f"{version_root}/docs/markdown/index.md"


def build_docs_html_path(
    tenant_slug: str,
    product_slug: str,
    version: str,
) -> str:
    """
    S3 key for HTML docs:
    tenants/{tenant_slug}/api_products/{product_slug}/versions/{version}/docs/html/index.html
    """
    version_root = build_version_root(tenant_slug, product_slug, version)
    return f"{version_root}/docs/html/index.html"


# ---------------------------------------------------------------------------
# Embeddings
# ---------------------------------------------------------------------------

def build_embeddings_root(
    tenant_slug: str,
    product_slug: str,
    version: str,
) -> str:
    """
    Root for embeddings:
    tenants/{tenant_slug}/api_products/{product_slug}/versions/{version}/embeddings/
    """
    version_root = build_version_root(tenant_slug, product_slug, version)
    return f"{version_root}/embeddings"


def build_embeddings_vectors_path(
    tenant_slug: str,
    product_slug: str,
    version: str,
) -> str:
    root = build_embeddings_root(tenant_slug, product_slug, version)
    return f"{root}/vectors.lance"


def build_embeddings_metadata_path(
    tenant_slug: str,
    product_slug: str,
    version: str,
) -> str:
    root = build_embeddings_root(tenant_slug, product_slug, version)
    return f"{root}/metadata.json"


# ---------------------------------------------------------------------------
# Diffs
# ---------------------------------------------------------------------------

def build_diff_path(
    tenant_slug: str,
    product_slug: str,
    from_version: str,
    to_version: str,
) -> str:
    """
    tenants/{tenant_slug}/api_products/{product_slug}/versions/{to_version}/diffs/v{from}-to-v{to}.json
    """
    version_root = build_version_root(tenant_slug, product_slug, to_version)
    return f"{version_root}/diffs/v{from_version}-to-v{to_version}.json"
