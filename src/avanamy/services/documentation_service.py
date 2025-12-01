# src/avanamy/services/documentation_service.py
import json
import logging
from opentelemetry import trace
from prometheus_client import Counter, REGISTRY
from avanamy.services.s3 import upload_bytes
from avanamy.services.documentation_renderer import render_markdown_to_html
from avanamy.services.documentation_generator import generate_markdown_from_normalized_spec
from avanamy.repositories.documentation_artifact_repository import DocumentationArtifactRepository


ARTIFACT_TYPE_API_MARKDOWN = "api_markdown"

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)

def safe_counter(name, documentation, **kwargs):
    """
    Ensures Prometheus metrics do not error during pytest collection.
    If a metric with the same name exists, return the existing instance.
    """
    try:
        return Counter(name, documentation, **kwargs)
    except ValueError:
        # metric already registered — reuse existing one
        return REGISTRY._names_to_collectors[name]
    

markdown_gen_counter = safe_counter(
    "avanamy_markdown_generation_total",
    "Number of markdown documentation generations"
)

def generate_and_store_markdown_for_spec(db, spec):
    """
    Generate Markdown documentation for a given spec.
    Store only Markdown in S3.
    Return the markdown key.
    """

    with tracer.start_as_current_span("generate_docs_for_spec") as span:
        markdown_gen_counter.inc()
        logger.info(f"Generating documentation for spec {spec.id}")

        if not spec.parsed_schema:
            logger.warning(f"Spec {spec.id} has no parsed_schema. Skipping doc generation.")
            return None

        try:
            schema = json.loads(spec.parsed_schema)
        except Exception:
            logger.exception(f"Spec {spec.id}: stored parsed_schema is not valid JSON")
            return None

        # --- Step 1: Generate Markdown ---
        markdown = generate_markdown_from_normalized_spec(schema)

        # --- Step 2: Store ONLY markdown (tests expect this) ---
        md_key = f"docs/{spec.id}/api.md"
        _, md_url = upload_bytes(
            md_key,
            markdown.encode("utf-8"),
            content_type="text/markdown"
        )

        # --- Step 3: Save reference in DB ---
        repo = DocumentationArtifactRepository()
        repo.create(
            db,
            api_spec_id=spec.id,
            artifact_type=ARTIFACT_TYPE_API_MARKDOWN,
            s3_path=md_key,
        )
        db.commit()

        return md_key

