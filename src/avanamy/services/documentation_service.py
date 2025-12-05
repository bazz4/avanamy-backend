# src/avanamy/services/documentation_service.py
import json
import logging
from uuid import UUID, uuid4
from opentelemetry import trace
from prometheus_client import Counter, REGISTRY

from avanamy.services.s3 import upload_bytes
from avanamy.services.documentation_renderer import render_markdown_to_html
from avanamy.services.documentation_generator import generate_markdown_from_normalized_spec
from avanamy.repositories.documentation_artifact_repository import DocumentationArtifactRepository
from avanamy.models.api_spec import ApiSpec
from avanamy.utils.filename_utils import slugify_filename

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
    "Number of markdown documentation generations"
)


def generate_and_store_markdown_for_spec(db, spec: ApiSpec):
    """
    Generate Markdown + HTML documentation for a spec.
    Upload *both* to S3.
    Update spec.documentation_html_s3_path.
    Store Markdown as an artifact.
    Returns the markdown key.
    """
    with tracer.start_as_current_span("docs.generate_and_store_markdown_for_spec") as span:
        span.set_attribute("api_spec.id", spec.id)
        span.set_attribute("tenant.id", str(getattr(spec, "tenant_id", "")))

        markdown_gen_counter.inc()
        logger.info(f"Generating documentation for spec {spec.id}")

        if not spec.parsed_schema:
            logger.warning("No parsed_schema; skipping documentation generation")
            return None

        # Parse stored JSON
        try:
            schema = json.loads(spec.parsed_schema)
        except Exception:
            logger.exception("parsed_schema is not valid JSON")
            return None
        
        # Tenant safety: requires tenant_id on every generated artifact
        tenant_id = getattr(spec, "tenant_id", None)
        if not tenant_id:
            logger.error(
                "Cannot generate documentation: spec %s has no tenant_id",
                spec.id
            )
            return None

        # Ensure proper UUID type (Postgres UUID type accepts python UUID)
        try:
            tenant_uuid = UUID(str(tenant_id))
        except Exception:
            logger.exception(
                "Invalid tenant_id value on spec %s: %s",
                spec.id,
                tenant_id
            )
            return None

        if not tenant_id:
            logger.error("Spec %s has no tenant_id; cannot generate tenant-scoped docs", spec.id)
            return None

        # --- Step 1: Markdown ---
        markdown = generate_markdown_from_normalized_spec(schema)

        md_key = (
            f"tenants/{tenant_id}/docs/{spec.id}/"
            f"{uuid4()}-{slugify_filename(spec.name)}.md"
        )
        _, md_url = upload_bytes(
            md_key,
            markdown.encode("utf-8"),
            content_type="text/markdown"
        )

        # --- Step 2: HTML ---
        html = render_markdown_to_html(markdown, title=f"{spec.name} API Docs")

        html_key = (
            f"tenants/{tenant_id}/docs/{spec.id}/"
            f"{uuid4()}-{slugify_filename(spec.name)}.html"
        )
        _, html_url = upload_bytes(
            html_key,
            html.encode("utf-8"),
            content_type="text/html"
        )

        # --- Step 3a: Save Markdown artifact in DB ---
        repo = DocumentationArtifactRepository()
        repo.create(
            db,
            tenant_id=tenant_uuid,
            api_spec_id=spec.id,
            artifact_type=ARTIFACT_TYPE_API_MARKDOWN,
            s3_path=md_key,
        )

        # --- Step 3b: Save HTML artifact in DB ---
        repo.create(
            db,
            tenant_id=tenant_uuid,
            api_spec_id=spec.id,
            artifact_type=ARTIFACT_TYPE_API_HTML,
            s3_path=html_key,
        )

        # --- Step 4: Update spec w/ HTML URL ---
        spec.documentation_html_s3_path = html_url
        db.commit()

        # Important: Do NOT refresh in tests (spec is not persisted)
        return md_key

def regenerate_all_docs_for_spec(db, spec):
    """
    Regenerate BOTH markdown and HTML documentation for a spec.
    Stores both artifacts in S3 and creates repo entries.
    Returns (markdown_key, html_key).
    """
    with tracer.start_as_current_span("docs.regenerate_all") as span:
        span.set_attribute("spec.id", spec.id)
        logger.info("Regenerating documentation for spec_id=%s", spec.id)

        if not spec.parsed_schema:
            logger.warning("Spec %s has no parsed_schema. Cannot regenerate docs.", spec.id)
            return None, None

        try:
            schema = json.loads(spec.parsed_schema)
        except Exception:
            logger.exception("Parsed schema for spec_id=%s is invalid JSON", spec.id)
            return None, None

        tenant_id = getattr(spec, "tenant_id", None)
        if not tenant_id:
            logger.error("Spec %s has no tenant_id; cannot regenerate tenant-scoped docs", spec.id)
            return None, None

        # --- Step 1: Generate markdown ---
        markdown = generate_markdown_from_normalized_spec(schema)

        md_key = (
            f"tenants/{tenant_id}/docs/{spec.id}/"
            f"{uuid4()}-{slugify_filename(spec.name)}.md"
        )
        _, md_url = upload_bytes(
            md_key,
            markdown.encode("utf-8"),
            content_type="text/markdown",
        )

        md_repo = DocumentationArtifactRepository()
        md_repo.create(
            db,
            api_spec_id=spec.id,
            tenant_id=tenant_id,
            artifact_type="api_markdown",
            s3_path=md_key,
        )

        # --- Step 2: Generate HTML ---
        html = render_markdown_to_html(markdown)

        html_key = (
            f"tenants/{tenant_id}/docs/{spec.id}/"
            f"{uuid4()}-{slugify_filename(spec.name)}.html"
        )
        _, html_url = upload_bytes(
            html_key,
            html.encode("utf-8"),
            content_type="text/html",
        )

        html_repo = DocumentationArtifactRepository()
        html_repo.create(
            db,
            api_spec_id=spec.id,
            tenant_id=tenant_id,
            artifact_type="api_html",
            s3_path=html_key,
        )

        db.commit()
        return md_key, html_key
