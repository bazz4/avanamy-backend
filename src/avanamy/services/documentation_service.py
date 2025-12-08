# src/avanamy/services/documentation_service.py

import json
import logging
from uuid import UUID

from sqlalchemy.orm import Session
from opentelemetry import trace
from prometheus_client import Counter, REGISTRY

from avanamy.models.documentation_artifact import DocumentationArtifact
from avanamy.models.provider import Provider
from avanamy.services.s3 import upload_bytes
from avanamy.services.documentation_renderer import render_markdown_to_html
from avanamy.services.documentation_generator import generate_markdown_from_normalized_spec
from avanamy.repositories.documentation_artifact_repository import DocumentationArtifactRepository
from avanamy.models.api_spec import ApiSpec
from avanamy.models.api_product import ApiProduct
from avanamy.models.tenant import Tenant
from avanamy.repositories.version_history_repository import VersionHistoryRepository
from avanamy.utils.filename_utils import slugify_filename
from avanamy.utils.s3_paths import (
    build_docs_markdown_path,
    build_docs_html_path,
)

ARTIFACT_TYPE_API_MARKDOWN = "api_markdown"
ARTIFACT_TYPE_API_HTML = "api_html"

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


def safe_counter(name, documentation, **kwargs):
    """Avoid duplicate metric registration in pytest."""
    try:
        return Counter(name, documentation, **kwargs)
    except ValueError:
        return REGISTRY._names_to_collectors[name]


markdown_gen_counter = safe_counter(
    "avanamy_markdown_generation_total",
    "Number of markdown documentation generations",
)


def generate_and_store_markdown_for_spec(db: Session, spec: ApiSpec):
    """
    Generate Markdown + HTML documentation for the *current* version of a spec.

    - Uses VersionHistoryRepository.current_version_label_for_spec to get 'vN'
    - Uses tenant + product slugs for S3 layout
    - Uploads markdown + HTML to S3
    - Upserts documentation_artifacts (no duplicates)
    - Updates spec.documentation_html_s3_path
    """
    with tracer.start_as_current_span("docs.generate_and_store_markdown_for_spec") as span:
        span.set_attribute("api_spec.id", spec.id)
        span.set_attribute("tenant.id", str(getattr(spec, "tenant_id", "")))

        markdown_gen_counter.inc()
        logger.info("Generating documentation for spec %s", spec.id)

        if not spec.parsed_schema:
            logger.warning("No parsed_schema; skipping documentation generation for spec %s", spec.id)
            return None

        # Parse stored JSON
        try:
            schema = json.loads(spec.parsed_schema)
        except Exception:
            logger.exception("parsed_schema is not valid JSON for spec %s", spec.id)
            return None

        # Tenant safety: requires tenant_id on every generated artifact
        tenant_id = getattr(spec, "tenant_id", None)
        if not tenant_id:
            logger.error("Cannot generate documentation: spec %s has no tenant_id", spec.id)
            return None
        logger.info("tenant_id raw value on spec = %s (%s)", tenant_id, type(tenant_id))
        # Ensure proper UUID type (Postgres UUID type accepts python UUID)
        try:
            tenant_uuid = UUID(str(tenant_id))
        except Exception:
            logger.exception(
                "Invalid tenant_id value on spec %s: %s",
                spec.id,
                tenant_id,
            )
            return None
        logger.info("tenant_uuid raw value on spec = %s (%s)", tenant_uuid, type(tenant_uuid))
        # Resolve product + tenant slugs
        product = db.query(ApiProduct).filter(ApiProduct.id == spec.api_product_id).first()
        if not product:
            logger.error("ApiProduct not found for spec_id=%s", spec.id)
            return None

        tenant = db.query(Tenant).filter(Tenant.id == product.tenant_id).first()
        if not tenant:
            logger.error("Tenant not found for product_id=%s", product.id)
            return None

        # Current label for this spec (e.g., "v1", "v2")
        version_label = VersionHistoryRepository.current_version_label_for_spec(db, spec.id)

        # --------------------------------------------------------------------
        # 1. Markdown
        # --------------------------------------------------------------------
        markdown = generate_markdown_from_normalized_spec(schema)

        provider = db.query(Provider).filter(Provider.id == product.provider_id).first()
        provider_slug = provider.slug
        spec_slug = slugify_filename(spec.name)

        md_key = build_docs_markdown_path(
            tenant_slug=tenant.slug,
            provider_slug=provider_slug,
            product_slug=product.slug,
            version=version_label,
            spec_id=spec.id,
            spec_slug=spec_slug,
        )
        _, md_url = upload_bytes(
            md_key,
            markdown.encode("utf-8"),
            content_type="text/markdown",
        )

        # --------------------------------------------------------------------
        # 2. HTML
        # --------------------------------------------------------------------
        html = render_markdown_to_html(markdown, title=f"{spec.name} API Docs")

        html_key = build_docs_html_path(
            tenant_slug=tenant.slug,
            provider_slug=provider_slug,
            product_slug=product.slug,
            version=version_label,
            spec_slug=spec_slug,
            spec_id=str(spec.id),
        )
        _, html_url = upload_bytes(
            html_key,
            html.encode("utf-8"),
            content_type="text/html",
        )

        # --------------------------------------------------------------------
        # 3. UPSERT documentation artifacts
        # --------------------------------------------------------------------
        repo = DocumentationArtifactRepository()

        # Markdown artifact
        existing_md = repo.get_latest(
            db=db,
            api_spec_id=spec.id,
            tenant_id=str(tenant_uuid),
            artifact_type=ARTIFACT_TYPE_API_MARKDOWN,
        )
        if existing_md:
            existing_md.s3_path = md_key
        else:
            repo.create(
                db=db,
                tenant_id=tenant_uuid,
                api_spec_id=spec.id,
                artifact_type=ARTIFACT_TYPE_API_MARKDOWN,
                s3_path=md_key,
            )

        # HTML artifact
        existing_html = repo.get_latest(
            db=db,
            tenant_id=str(tenant_uuid),
            api_spec_id=spec.id,
            artifact_type=ARTIFACT_TYPE_API_HTML,
        )
        if existing_html:
            existing_html.s3_path = html_key
        else:
            repo.create(
                db=db,
                tenant_id=tenant_uuid,
                api_spec_id=spec.id,
                artifact_type=ARTIFACT_TYPE_API_HTML,
                s3_path=html_key,
            )

        # --------------------------------------------------------------------
        # 4. Update spec with HTML URL and commit
        # --------------------------------------------------------------------
        spec.documentation_html_s3_path = html_url
        db.commit()

        return md_key


def regenerate_all_docs_for_spec(db: Session, spec: ApiSpec):
    """
    Regenerate docs for the current version of a spec *without* creating a new
    VersionHistory row. This is essentially an idempotent re-run of
    generate_and_store_markdown_for_spec.
    """
    with tracer.start_as_current_span("docs.regenerate_all") as span:
        span.set_attribute("spec.id", spec.id)
        logger.info("Regenerating documentation for spec_id=%s", spec.id)

    md_key = generate_and_store_markdown_for_spec(db, spec)

    # Derive html_key from the same version/paths used above
    if md_key is None:
        return None, None

    # To compute html_key, we need version + slugs again
    product = db.query(ApiProduct).filter(ApiProduct.id == spec.api_product_id).first()
    if not product:
        logger.error("ApiProduct not found in regenerate_all_docs_for_spec for spec_id=%s", spec.id)
        return md_key, None

    tenant = db.query(Tenant).filter(Tenant.id == product.tenant_id).first()
    if not tenant:
        logger.error("Tenant not found in regenerate_all_docs_for_spec for product_id=%s", product.id)
        return md_key, None

    version_label = VersionHistoryRepository.current_version_label_for_spec(db, spec.id)

    # -----------------------------
    # Compute provider + spec slugs
    # -----------------------------
    provider = db.query(Provider).filter(Provider.id == product.provider_id).first()
    if not provider:
        logger.error("Provider not found in regenerate_all_docs_for_spec for provider_id=%s", product.provider_id)
        return md_key, None

    provider_slug = provider.slug
    spec_slug = slugify_filename(spec.name)
    spec_id = spec.id

    # -----------------------------
    # Build HTML docs S3 path
    # -----------------------------
    html_key = build_docs_html_path(
        tenant_slug=tenant.slug,
        provider_slug=provider_slug,
        product_slug=product.slug,
        version=version_label,
        spec_id=spec_id,
        spec_slug=spec_slug,
    )

    # -----------------------------
    # Build Markdown docs S3 path
    # -----------------------------
    md_key_final = build_docs_markdown_path(
        tenant_slug=tenant.slug,
        provider_slug=provider_slug,
        product_slug=product.slug,
        version=version_label,
        spec_id=spec_id,
        spec_slug=spec_slug,
    )

    return md_key_final, html_key
