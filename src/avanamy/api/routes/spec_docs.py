from __future__ import annotations

from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from avanamy.db.database import SessionLocal
from avanamy.auth.clerk import get_current_tenant_id
from avanamy.models.api_spec import ApiSpec
from avanamy.models.api_product import ApiProduct
from avanamy.models.provider import Provider
from avanamy.repositories.documentation_artifact_repository import DocumentationArtifactRepository
from avanamy.repositories.version_history_repository import VersionHistoryRepository

router = APIRouter(
    prefix="/specs",
    tags=["Docs"],
)


# ---------------------------------------------------------------------------
# DB dependency
# ---------------------------------------------------------------------------

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Response model
# ---------------------------------------------------------------------------

class SpecDocsOut(BaseModel):
    spec_id: UUID
    version: str
    markdown_s3_url: str
    html_s3_url: str


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@router.get(
    "/{spec_id}/docs",
    response_model=SpecDocsOut,
)
def get_docs_for_spec(
    spec_id: UUID,
    tenant_id: str = Depends(get_current_tenant_id),
    db: Session = Depends(get_db),
):
    """
    Fetch Markdown + HTML docs for the *current* version of a spec.
    """

    # Tenant validation: spec → product → provider → tenant
    spec = (
        db.query(ApiSpec)
        .join(ApiProduct, ApiProduct.id == ApiSpec.api_product_id)
        .join(Provider, Provider.id == ApiProduct.provider_id)
        .filter(
            ApiSpec.id == spec_id,
            Provider.tenant_id == tenant_id,
        )
        .first()
    )

    if not spec:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API spec not found for this tenant",
        )

    # Resolve current version label (vN)
    version_label = VersionHistoryRepository.current_version_label_for_spec(
        db, spec.id
    )

    repo = DocumentationArtifactRepository()

    markdown = repo.get_latest(
        db=db,
        api_spec_id=str(spec.id),
        tenant_id=tenant_id,
        artifact_type="api_markdown",
    )

    html = repo.get_latest(
        db=db,
        api_spec_id=str(spec.id),
        tenant_id=tenant_id,
        artifact_type="api_html",
    )

    if not markdown or not html:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Documentation not found for this spec",
        )

    return SpecDocsOut(
        spec_id=spec.id,
        version=version_label,
        markdown_s3_url=markdown.s3_path,
        html_s3_url=html.s3_path,
    )
