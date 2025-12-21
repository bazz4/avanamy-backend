# src/avanamy/api/routes/spec_versions.py

from __future__ import annotations

from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from avanamy.db.database import SessionLocal
from avanamy.api.dependencies.tenant import get_tenant_id
from avanamy.models.api_spec import ApiSpec
from avanamy.models.api_product import ApiProduct
from avanamy.models.provider import Provider
from avanamy.models.version_history import VersionHistory

router = APIRouter(
    prefix="/api-specs",
    tags=["API Specs"],
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
# Pydantic models
# ---------------------------------------------------------------------------

class SpecVersionOut(BaseModel):
    version: int
    label: str
    created_at: str
    changelog: str | None = None
    diff: dict | None = None  # Diff information showing changes from previous version

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@router.get(
    "/{spec_id}/versions",
    response_model=List[SpecVersionOut],
)
def list_versions_for_spec(
    spec_id: UUID,
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
):
    """
    List all historical versions for a given API spec.
    """
    # Validate tenant ownership:
    # spec → product → provider → tenant
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

    versions = (
        db.query(VersionHistory)
        .filter(VersionHistory.api_spec_id == spec_id)
        .order_by(VersionHistory.version.asc())
        .all()
    )

    return [
        {
            "version": vh.version,
            "label": f"v{vh.version}",
            "created_at": vh.created_at.isoformat(),
            "changelog": vh.changelog,
            "diff": vh.diff,
        }
        for vh in versions
    ]