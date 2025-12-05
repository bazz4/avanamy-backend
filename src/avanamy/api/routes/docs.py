# src/avanamy/api/routes/docs.py

from __future__ import annotations

import logging
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse, HTMLResponse
from sqlalchemy.orm import Session

from opentelemetry import trace
from prometheus_client import Counter, REGISTRY

from avanamy.db.database import SessionLocal
from avanamy.repositories.documentation_artifact_repository import (
    DocumentationArtifactRepository,
)
from avanamy.services.s3 import download_bytes
from avanamy.api.dependencies.tenant import get_tenant_id
from avanamy.models.api_spec import ApiSpec

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)

router = APIRouter(prefix="/docs", tags=["Documentation"])


# ----------------------------------------------------------
# Safe Prometheus counter helper
# ----------------------------------------------------------
def safe_counter(name, documentation, **kwargs):
    try:
        return Counter(name, documentation, **kwargs)
    except ValueError:
        return REGISTRY._names_to_collectors[name]


markdown_requests = safe_counter(
    "avanamy_docs_markdown_requests_total",
    "Count of markdown documentation fetch requests",
)

html_requests = safe_counter(
    "avanamy_docs_html_requests_total",
    "Count of HTML documentation fetch requests",
)


# ----------------------------------------------------------
# DB dependency
# ----------------------------------------------------------
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ========================================================================
# LEGACY ENDPOINT (REQUIRED BY TESTS)
# GET /docs/{spec_id}  → returns MARKDOWN
# ========================================================================
@router.get("/specs/{spec_id}", response_class=PlainTextResponse)
def get_original_spec(
    spec_id: int,
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
):
    """
    Legacy endpoint: returns MARKDOWN only.
    Tests rely on this exact behavior.
    """
    markdown_requests.inc()
    logger.info("Fetching legacy markdown for spec_id=%s", spec_id)

    with tracer.start_as_current_span("docs.get_legacy_markdown") as span:
        span.set_attribute("spec.id", spec_id)

        repo = DocumentationArtifactRepository()
        artifact = repo.get_latest_by_spec_id(
            db, spec_id, tenant_id, artifact_type="api_markdown"
        )

        if not artifact:
            logger.warning("Markdown artifact missing for spec_id=%s", spec_id)
            raise HTTPException(
                status_code=404,
                detail="Documentation not found",  # EXACT string required by tests
            )

        md_bytes = download_bytes(artifact.s3_path)
        logger.debug("Fetched markdown bytes for spec_id=%s", spec_id)

        return PlainTextResponse(
            content=md_bytes.decode("utf-8"),
            media_type="text/markdown"
        )


# ========================================================================
# MODERN ENDPOINTS (FOR YOUR PRODUCT)
# ========================================================================

# Get raw markdown
@router.get("/docs/{spec_id}/markdown", response_class=PlainTextResponse)
def get_markdown_doc(
    spec_id: int,
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
):
    markdown_requests.inc()
    logger.info("Fetching markdown for spec_id=%s", spec_id)

    with tracer.start_as_current_span("docs.get_markdown") as span:
        span.set_attribute("tenant.id", tenant_id)
        span.set_attribute("api_spec.id", spec_id)

        repo = DocumentationArtifactRepository()
        artifact = repo.get_latest_by_spec_id(
            db, spec_id, tenant_id, artifact_type="api_markdown"
        )

        if not artifact:
            raise HTTPException(
                status_code=404,
                detail="Markdown documentation not found",
            )

        return download_bytes(artifact.s3_path).decode("utf-8")

# Get generated HTML
@router.get("/docs/{spec_id}/html", response_class=HTMLResponse)
def get_docs_html(
    spec_id: int,
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
):
    html_requests.inc()
    logger.info("Fetching HTML for spec_id=%s", spec_id)

    with tracer.start_as_current_span("api.get_docs_html") as span:
        span.set_attribute("tenant.id", tenant_id)
        span.set_attribute("api_spec.id", spec_id)

        repo = DocumentationArtifactRepository()
        artifact = repo.get_latest_by_spec_id(
            db, spec_id, tenant_id, artifact_type="api_html"
        )

        if not artifact:
            raise HTTPException(
                status_code=404,
                detail="HTML documentation not found",
            )

        return HTMLResponse(
            content=download_bytes(artifact.s3_path).decode("utf-8")
        )
