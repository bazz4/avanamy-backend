# src/avanamy/api/routes/spec_versions.py

from __future__ import annotations

from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from avanamy.db.database import SessionLocal
from avanamy.auth.clerk import get_current_tenant_id
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
    summary: str | None = None  # AI-generated summary of changes

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@router.get(
    "/{spec_id}/versions",
    response_model=List[SpecVersionOut],
)
async def list_versions_for_spec(
    spec_id: UUID,
    tenant_id: str = Depends(get_current_tenant_id),
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
            "summary": vh.summary,
        }
        for vh in versions
    ]

@router.get(
    "/{spec_id}/versions/{version_id}",
    response_model=SpecVersionOut,
)
async def get_version_detail(
    spec_id: UUID,
    version_id: int,
    tenant_id: str = Depends(get_current_tenant_id),
    db: Session = Depends(get_db),
):
    """
    Get detailed information about a specific version, including diff and summary.
    """
    # Validate tenant ownership
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

    version = (
        db.query(VersionHistory)
        .filter(
            VersionHistory.api_spec_id == spec_id,
            VersionHistory.id == version_id,
        )
        .first()
    )

    if not version:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Version not found",
        )

    return {
        "version": version.version,
        "label": f"v{version.version}",
        "created_at": version.created_at.isoformat(),
        "changelog": version.changelog,
        "diff": version.diff,
        "summary": version.summary,
    }


@router.get(
    "/{spec_id}/versions/{version_number}/diff",
)
async def get_version_diff(
    spec_id: UUID,
    version_number: int,
    tenant_id: str = Depends(get_current_tenant_id),
    db: Session = Depends(get_db),
):
    """
    Get the raw diff for a specific version by version number.
    Returns the JSON diff object showing what changed from the previous version.
    """
    # Validate tenant ownership
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

    version = (
        db.query(VersionHistory)
        .filter(
            VersionHistory.api_spec_id == spec_id,
            VersionHistory.version == version_number,  # Changed from .id to .version
        )
        .first()
    )

    if not version:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Version not found",
        )

    if not version.diff:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No diff available for this version",
        )

    return {
        "version_id": version.id,
        "version": version.version,
        "diff": version.diff,
        "summary": version.summary,
        "created_at": version.created_at.isoformat(),
    }

@router.get(
    "/{spec_id}/versions/{version_number}/schema",
)
async def get_version_schema(
    spec_id: UUID,
    version_number: int,
    tenant_id: str = Depends(get_current_tenant_id),
    db: Session = Depends(get_db),
):
    """
    Get the full parsed schema for a specific version.
    Used for full schema comparison view.
    """
    # Validate tenant ownership
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

    # For version 1, get the original spec
    if version_number == 1:
        import json
        schema = json.loads(spec.parsed_schema) if spec.parsed_schema else {}
        return {
            "version": 1,
            "schema": schema,
        }

    # For other versions, reconstruct schema by applying diffs
    # For now, we'll just return the current spec's parsed_schema
    # In a production system, you'd store each version's full schema
    import json
    schema = json.loads(spec.parsed_schema) if spec.parsed_schema else {}
    
    return {
        "version": version_number,
        "schema": schema,
    }

# ADD THESE TWO ENDPOINTS TO spec_versions.py AT THE END OF THE FILE
# (After the last existing endpoint)


@router.get(
    "/{spec_id}/versions/{version_number}/original-spec",
)
async def get_original_spec_for_version(
    spec_id: UUID,
    version_number: int,
    tenant_id: str = Depends(get_current_tenant_id),
    db: Session = Depends(get_db),
):
    """
    Get the original OpenAPI spec file for a specific version.
    Fetches the file from S3 using the documentation_artifact record.
    """
    from avanamy.models.documentation_artifact import DocumentationArtifact
    from avanamy.services.s3 import download_bytes
    import json
    import yaml
    
    # Validate tenant ownership
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

    # Get the version history
    version = (
        db.query(VersionHistory)
        .filter(
            VersionHistory.api_spec_id == spec_id,
            VersionHistory.version == version_number,
        )
        .first()
    )

    if not version:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Version not found",
        )

    # Get the original spec artifact
    artifact = (
        db.query(DocumentationArtifact)
        .filter(
            DocumentationArtifact.version_history_id == version.id,
            DocumentationArtifact.artifact_type == "original_spec",
        )
        .first()
    )

    if not artifact:
        # Check if this version was created before artifact storage was implemented
        # by looking at the creation date or checking for normalized_spec artifact
        normalized_artifact = (
            db.query(DocumentationArtifact)
            .filter(
                DocumentationArtifact.version_history_id == version.id,
                DocumentationArtifact.artifact_type == "normalized_spec",
            )
            .first()
        )
        
        error_detail = {
            "error": "Original spec artifact not found for this version",
            "version": version_number,
            "created_at": version.created_at.isoformat() if version.created_at else None,
            "is_legacy_version": normalized_artifact is not None,  # Has other artifacts but not original_spec
            "suggestion": "This version was created before original spec storage was implemented. Upload a new version or re-upload this spec to enable full schema comparison."
        }
        
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=error_detail,
        )

    # Download from S3
    try:
        spec_bytes = download_bytes(artifact.s3_path)
        spec_text = spec_bytes.decode('utf-8')
        
        # Try to parse as JSON/YAML
        try:
            spec_data = json.loads(spec_text)
        except json.JSONDecodeError:
            # If not JSON, try YAML
            spec_data = yaml.safe_load(spec_text)
        
        return {
            "version": version_number,
            "spec": spec_data,
            "s3_path": artifact.s3_path,
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch spec from S3: {str(e)}",
        )


@router.get(
    "/{spec_id}/versions/{version_number}/compare",
)
async def compare_two_versions(
    spec_id: UUID,
    version_number: int,
    compare_with: int,
    tenant_id: str = Depends(get_current_tenant_id),
    db: Session = Depends(get_db),
):
    """
    Compare two versions of a spec side-by-side.
    Returns both original specs for client-side diff computation.
    
    Query params:
        compare_with: The version number to compare against (usually version_number - 1)
    """
    from avanamy.models.documentation_artifact import DocumentationArtifact
    from avanamy.services.s3 import download_bytes
    import json
    import yaml
    
    # Validate tenant ownership
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

    # Helper function to get spec for a version
    def get_spec_for_version(ver_num: int):
        version = (
            db.query(VersionHistory)
            .filter(
                VersionHistory.api_spec_id == spec_id,
                VersionHistory.version == ver_num,
            )
            .first()
        )
        
        if not version:
            return None
            
        artifact = (
            db.query(DocumentationArtifact)
            .filter(
                DocumentationArtifact.version_history_id == version.id,
                DocumentationArtifact.artifact_type == "original_spec",
            )
            .first()
        )
        
        if not artifact:
            return None
            
        try:
            spec_bytes = download_bytes(artifact.s3_path)
            spec_text = spec_bytes.decode('utf-8')
            
            try:
                return json.loads(spec_text)
            except json.JSONDecodeError:
                return yaml.safe_load(spec_text)
        except:
            return None
    
    # Get both versions
    current_spec = get_spec_for_version(version_number)
    previous_spec = get_spec_for_version(compare_with)
    
    if not current_spec:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Spec not found for version {version_number}",
        )
    
    if not previous_spec:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Spec not found for version {compare_with}",
        )
    
    return {
        "current_version": version_number,
        "previous_version": compare_with,
        "current_spec": current_spec,
        "previous_spec": previous_spec,
    }
