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
    spec_id: UUID,
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
    spec_id: UUID,
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
    spec_id: UUID,
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

@router.get("/{spec_id}/versions/{version_id}")
async def get_version_documentation(
    spec_id: UUID,
    version_id: int,
    format: str = "html",  # "html" or "markdown"
    db: Session = Depends(get_db),
):
    """
    Get documentation for a specific version.
    
    This allows viewing historical docs for any version, not just the latest.
    """
    logger.info(f"Fetching {format} docs for spec {spec_id}, version {version_id}")
    
    with tracer.start_as_current_span("docs.get_version_documentation") as span:
        span.set_attribute("spec.id", str(spec_id))
        span.set_attribute("version.id", version_id)
        span.set_attribute("format", format)

        spec = db.query(ApiSpec).filter(ApiSpec.id == spec_id).first()

        if not spec:
            raise HTTPException(404, "API spec not found")
        
        # Get version history
        from avanamy.models.version_history import VersionHistory
        version = db.query(VersionHistory).filter(
            VersionHistory.api_spec_id == spec_id,
            VersionHistory.version == version_id
        ).first()
        
        if not version:
            raise HTTPException(404, f"Version {version_id} not found")
        
        # Get documentation artifact
        from avanamy.models.documentation_artifact import DocumentationArtifact
        artifact_type = "api_markdown" if format == "markdown" else "api_html"
        
        artifact = db.query(DocumentationArtifact).filter(
            DocumentationArtifact.version_history_id == version.id,
            DocumentationArtifact.artifact_type == artifact_type
        ).first()
        
        if not artifact:
            raise HTTPException(
                404,
                f"No {format} documentation found for version {version_id}"
            )
        
        # Fetch from S3
        content_bytes = download_bytes(artifact.s3_path)
        content = content_bytes.decode('utf-8')
        
        # Track metrics
        if format == "html":
            html_requests.inc()
        else:
            markdown_requests.inc()
        
         # Return raw HTML/Markdown for browser viewing
        logger.info(f"Returning {format} documentation, length: {len(content)} bytes")
        
        if format == "html":
            return HTMLResponse(content=content)
        else:
            return PlainTextResponse(content=content)


@router.get("/{spec_id}/versions/{version_id}/available")
async def get_available_documentation_formats(
    spec_id: UUID,
    version_id: int,
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db)
):
    """Check which documentation formats are available for a version."""
    
    logger.info(f"Checking available docs for spec {spec_id}, version {version_id}")
    
    # ADD THIS: Validate tenant ownership
    spec = db.query(ApiSpec).filter(
        ApiSpec.id == spec_id,
        ApiSpec.tenant_id == tenant_id
    ).first()
    
    if not spec:
        raise HTTPException(404, "API spec not found")
    
    # Rest of the code stays the same...
    from avanamy.models.version_history import VersionHistory
    version = db.query(VersionHistory).filter(
        VersionHistory.api_spec_id == spec_id,
        VersionHistory.version == version_id
    ).first()
    
    if not version:
        raise HTTPException(404, f"Version {version_id} not found")
    
    # Get all doc artifacts for this version
    from avanamy.models.documentation_artifact import DocumentationArtifact
    artifacts = db.query(DocumentationArtifact).filter(
        DocumentationArtifact.version_history_id == version.id,
        DocumentationArtifact.artifact_type.in_(['api_markdown', 'api_html'])
    ).all()
    
    available = {
        "markdown": False,
        "html": False
    }
    
    for artifact in artifacts:
        if artifact.artifact_type == "api_markdown":
            available["markdown"] = True
        elif artifact.artifact_type == "api_html":
            available["html"] = True
    
    return {
        "spec_id": str(spec_id),
        "version": version_id,
        "available_formats": available,
        "total_artifacts": len(artifacts)
    }

@router.get("/{spec_id}/latest")
async def get_latest_documentation(
    spec_id: UUID,
    format: str = "html",
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db)
):
    """
    Get documentation for the latest version of a spec.
    
    Convenience endpoint so frontend doesn't need to find latest version first.
    """
    # Validate tenant ownership
    spec = db.query(ApiSpec).filter(
        ApiSpec.id == spec_id,
        ApiSpec.tenant_id == tenant_id
    ).first()
    
    if not spec:
        raise HTTPException(404, "API spec not found")
    
    # Get latest version
    from avanamy.models.version_history import VersionHistory
    latest_version = db.query(VersionHistory).filter(
        VersionHistory.api_spec_id == spec_id
    ).order_by(VersionHistory.version.desc()).first()
    
    if not latest_version:
        raise HTTPException(404, "No versions found for this spec")
    
    # Call the version-specific endpoint
    return await get_version_documentation(
        spec_id=spec_id,
        version_id=latest_version.version,
        format=format,
        tenant_id=tenant_id,
        db=db
    )