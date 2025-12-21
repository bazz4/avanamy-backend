# src/avanamy/utils/s3_paths.py

from __future__ import annotations

from uuid import UUID
from avanamy.utils.filename_utils import slugify_filename, get_file_extension


def build_tenant_root(tenant_slug: str) -> str:
    return f"tenants/{tenant_slug}"


def build_product_root(tenant_slug: str, provider_slug: str, product_slug: str) -> str:
    tenant_root = build_tenant_root(tenant_slug)
    return f"{tenant_root}/providers/{provider_slug}/api_products/{product_slug}"


def build_version_root(tenant_slug: str, provider_slug: str, product_slug: str, version: str) -> str:
    product_root = build_product_root(tenant_slug, provider_slug, product_slug)
    return f"{product_root}/versions/{version}"


# ---------------------------------------------------------------------------
# Specs
# ---------------------------------------------------------------------------

def build_spec_upload_path(
    tenant_slug: str,
    provider_slug: str,
    product_slug: str,
    version: str,
    spec_id: UUID,
    spec_slug: str,
    ext: str
) -> str:

    """
    New S3 path for uploaded spec files:
    tenants/{tenant_slug}/api_products/{product_slug}/versions/{version}/specs/{spec_slug}/{spec_id}-{spec_slug}{ext}
    """
    version_root = build_version_root(tenant_slug, provider_slug, product_slug, version)
    filename = f"{spec_id}-{spec_slug}{ext}"
    return f"{version_root}/specs/{spec_id}/{spec_id}-{spec_slug}{ext}"

# ---------------------------------------------------------------------------
# Docs (Markdown + HTML)
# ---------------------------------------------------------------------------

def build_docs_markdown_path(tenant_slug, provider_slug, product_slug, version, spec_id, spec_slug):
    version_root = build_version_root(tenant_slug, provider_slug, product_slug, version)
    return f"{version_root}/docs/markdown/{spec_id}-{spec_slug}.md"

def build_docs_html_path(tenant_slug, provider_slug, product_slug, version, spec_id, spec_slug):
    version_root = build_version_root(tenant_slug, provider_slug, product_slug, version)
    return f"{version_root}/docs/html/{spec_id}-{spec_slug}.html"

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

def build_normalized_spec_path(
    tenant_slug: str,
    provider_slug: str,
    product_slug: str,
    version: str,
    spec_id: UUID,
    spec_slug: str,
) -> str:
    """
    S3 path for normalized spec artifacts:
    tenants/{tenant_slug}/providers/{provider_slug}/api_products/{product_slug}/versions/{version}/normalized/{spec_id}-{spec_slug}.json
    """
    version_root = build_version_root(tenant_slug, provider_slug, product_slug, version)
    return f"{version_root}/normalized/{spec_id}-{spec_slug}.json"