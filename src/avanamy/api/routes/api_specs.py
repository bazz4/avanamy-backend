from __future__ import annotations

import json
import logging
from fastapi.responses import HTMLResponse, PlainTextResponse
from opentelemetry import trace
from prometheus_client import Counter, REGISTRY
from uuid import UUID
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, Depends, Form, Query, UploadFile, File, HTTPException, Form
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from avanamy.auth.clerk import get_current_tenant_id
from avanamy.db.database import SessionLocal
from avanamy.models.api_spec import ApiSpec
from avanamy.models.version_history import VersionHistory
from avanamy.repositories.api_spec_repository import ApiSpecRepository
from avanamy.services.impact_analysis_service import ImpactAnalysisService
from avanamy.services.api_spec_service import store_api_spec_file, update_api_spec_file
from avanamy.services.documentation_service import regenerate_all_docs_for_spec
from avanamy.repositories.version_history_repository import VersionHistoryRepository
from avanamy.db.database import get_db

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)

router = APIRouter(
    prefix="/api-specs",
    tags=["API Specs"],
)

def serialize_spec(spec):
    """
    Convert ORM ApiSpec → ApiSpecOut dict.
    Ensures parsed_schema is a dict, not a raw JSON string.
    """
    data = {
        "id": spec.id,
        "tenant_id": spec.tenant_id,
        "name": spec.name,
        "version": spec.version,
        "description": spec.description,
        "original_file_s3_path": spec.original_file_s3_path,
        "parsed_schema": None,
    }

    if spec.parsed_schema:
        try:
            data["parsed_schema"] = json.loads(spec.parsed_schema)
        except Exception:
            data["parsed_schema"] = None

    return data


# --- DB dependency -----------------------------------------------------------

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# --- Pydantic models ---------------------------------------------------------

class ApiSpecOut(BaseModel):
    id: UUID
    name: str
    version: Optional[str] = None
    description: Optional[str] = None
    original_file_s3_path: str
    parsed_schema: Dict[str, Any] | None = None

    class Config:
        from_attributes = True


# -----------------------------------------------------------------------------
#  🚨 IMPORTANT: STATIC ROUTES MUST COME *BEFORE* DYNAMIC ONES
# -----------------------------------------------------------------------------

@router.post("/upload", response_model=ApiSpecOut)
async def upload_api_spec(
    file: UploadFile = File(...),
    api_product_id: UUID = Query(...),   # ⬅️ REQUIRED
    provider_id: Optional[UUID] = Query(None),  # ⬅️ OPTIONAL
    name: Optional[str] = None,
    version: Optional[str] = None,
    description: Optional[str] = None,
    tenant_id: str = Depends(get_current_tenant_id),
    db: Session = Depends(get_db),
):
    """
    Upload an API spec file and store in S3 + DB.
    """
    contents = await file.read()

    logger.info("API upload handler start: filename=%s", file.filename)
    with tracer.start_as_current_span("api.upload_api_spec") as span:
        span.set_attribute("file.size", len(contents) if contents is not None else 0)

    spec = await store_api_spec_file(
        db=db,
        file_bytes=contents,
        filename=file.filename,
        content_type=file.content_type,
        tenant_id=tenant_id,
        api_product_id=api_product_id,   
        provider_id=provider_id,         
        name=name,
        version=version,
        description=description,
        parsed_schema=None,
    )

    # 🚨 Prevent serialize_spec(None)
    if spec is None:
        logger.error("upload_api_spec: spec creation failed (store_api_spec_file returned None)")
        raise HTTPException(
            status_code=400,
            detail="Failed to create API spec. Ensure api_product_id is set and valid."
        )

    logger.info(
        "API upload handler complete: spec_id=%s filename=%s",
        getattr(spec, "id", None),
        getattr(spec, "name", None),
    )

    return serialize_spec(spec)

@router.post("/{spec_id}/upload-new-version", response_model=ApiSpecOut)
async def upload_new_api_spec_version(
    spec_id: UUID,
    file: UploadFile = File(...),
    version: Optional[str] = None,
    description: Optional[str] = None,
    tenant_id: str = Depends(get_current_tenant_id),
    db: Session = Depends(get_db),
):
    """
    Upload a new version of an existing API spec.

    Behavior:
      - validates that the spec belongs to the tenant
      - parses + normalizes + stores the new spec file
      - updates the existing ApiSpec row
      - regenerates Markdown + HTML docs
      - appends a VersionHistory row
      - triggers impact analysis if breaking changes detected
    """
    contents = await file.read()

    logger.info(
        "API new-version upload handler start: spec_id=%s filename=%s",
        spec_id,
        file.filename,
    )

    with tracer.start_as_current_span("api.upload_new_api_spec_version") as span:
        span.set_attribute("spec.id", spec_id)
        span.set_attribute("tenant.id", tenant_id)
        span.set_attribute("file.size", len(contents) if contents is not None else 0)

        # 1. Load existing spec for this tenant
        spec = ApiSpecRepository.get_by_id(
            db=db,
            spec_id=spec_id,
            tenant_id=tenant_id,
        )

        if not spec:
            logger.warning(
                "Spec not found for new-version upload spec_id=%s tenant_id=%s",
                spec_id,
                tenant_id,
            )
            raise HTTPException(status_code=404, detail="API spec not found")

        # 2. Determine effective version / description
        effective_version = version or spec.version
        effective_description = description if description is not None else spec.description

        # 3. Update the spec record + regenerate docs
        updated_spec = await update_api_spec_file(
            db=db,
            spec=spec,
            file_bytes=contents,
            filename=file.filename,
            content_type=file.content_type,
            tenant_id=tenant_id,
            version=effective_version,
            description=effective_description,
        )
        
        # 4. Get the latest version history entry that was just created
        latest_version = (
            db.query(VersionHistory)
            .filter(VersionHistory.api_spec_id == spec_id)
            .order_by(VersionHistory.version.desc())
            .first()
        )
        
        # 5. Trigger impact analysis if there's a diff with breaking changes
        if latest_version and latest_version.diff:
            logger.info(
                "Triggering impact analysis for spec=%s version=%s",
                spec_id,
                latest_version.version,
            )
            
            try:
                # Check if diff has breaking changes
                diff_data = latest_version.diff
                if isinstance(diff_data, str):
                    import json
                    diff_data = json.loads(diff_data)
                
                has_breaking = diff_data.get("breaking", False)
                
                if has_breaking:
                    logger.info("Breaking changes detected, running impact analysis")
                    
                    # Run impact analysis
                    impact_service = ImpactAnalysisService(db)
                    impact_result = await impact_service.analyze_breaking_changes(
                        tenant_id=tenant_id,
                        diff=diff_data,
                        spec_id=spec_id,
                        version_history_id=latest_version.id,
                        created_by_user_id=tenant_id,  # User who uploaded
                    )
                    
                    logger.info(
                        "Impact analysis complete: has_impact=%s affected_repos=%d",
                        impact_result.has_impact,
                        impact_result.total_affected_repos,
                    )
                else:
                    logger.info("No breaking changes detected, skipping impact analysis")
                    
            except Exception as e:
                # Don't fail the upload if impact analysis fails
                logger.error(
                    "Impact analysis failed for spec=%s version=%s: %s",
                    spec_id,
                    latest_version.version,
                    str(e),
                    exc_info=True,
                )

    logger.info(
        "API new-version upload handler complete: spec_id=%s filename=%s",
        spec_id,
        getattr(updated_spec, "name", None),
    )

    return serialize_spec(updated_spec)

@router.get("/", response_model=List[ApiSpecOut])
async def list_api_specs(
    tenant_id: str = Depends(get_current_tenant_id),
    db: Session = Depends(get_db),
):
    with tracer.start_as_current_span("api.list_api_specs") as span:
        span.set_attribute("tenant.id", tenant_id)

        specs = (
            db.query(ApiSpec)
            .filter(ApiSpec.tenant_id == tenant_id)
            .order_by(ApiSpec.created_at.desc())
            .all()
        )

    return [serialize_spec(s) for s in specs]

@router.get("/enriched", response_model=List[dict])
async def list_api_specs_enriched(
    tenant_id: str = Depends(get_current_tenant_id),
    db: Session = Depends(get_db),
):
    """
    Get all API specs with enriched provider/product context and version information.
    Returns specs with provider names, product names, latest version info, and breaking change indicators.
    """
    from avanamy.models.api_product import ApiProduct
    from avanamy.models.provider import Provider
    from avanamy.models.version_history import VersionHistory
    
    with tracer.start_as_current_span("api.list_api_specs_enriched") as span:
        span.set_attribute("tenant.id", tenant_id)

        # Get all specs with their products and providers using ORM
        specs_query = (
            db.query(
                ApiSpec,
                ApiProduct.provider_id,
                Provider.name.label('provider_name'),
                Provider.slug.label('provider_slug'),
                ApiProduct.name.label('product_name'),
                ApiProduct.slug.label('product_slug')
            )
            .join(ApiProduct, ApiSpec.api_product_id == ApiProduct.id)
            .join(Provider, ApiProduct.provider_id == Provider.id)
            .filter(ApiSpec.tenant_id == tenant_id)
            .all()
        )
        
        enriched_specs = []
        
        for spec, provider_id, provider_name, provider_slug, product_name, product_slug in specs_query:
            # Get latest version info
            latest_version = (
                db.query(VersionHistory)
                .filter(VersionHistory.api_spec_id == spec.id)
                .order_by(VersionHistory.version.desc())
                .first()
            )
            
            # Count total versions
            total_versions = (
                db.query(VersionHistory)
                .filter(VersionHistory.api_spec_id == spec.id)
                .count()
            )
            
            # Check for breaking changes
            has_breaking = False
            if latest_version and latest_version.diff:
                # Check if diff JSON has breaking: true
                diff_data = latest_version.diff
                if isinstance(diff_data, dict):
                    has_breaking = diff_data.get('breaking', False)
                elif isinstance(diff_data, str):
                    import json
                    try:
                        diff_dict = json.loads(diff_data)
                        has_breaking = diff_dict.get('breaking', False)
                    except:
                        pass
            
            enriched_specs.append({
                "id": str(spec.id),
                "api_product_id": str(spec.api_product_id),
                "name": spec.name,
                "description": spec.description,
                "provider_id": str(provider_id),
                "provider_name": provider_name,
                "provider_slug": provider_slug,
                "product_name": product_name,
                "product_slug": product_slug,
                "latest_version": latest_version.version if latest_version else None,
                "latest_version_created_at": latest_version.created_at.isoformat() if latest_version else None,
                "total_versions": total_versions,
                "has_breaking_changes": has_breaking,
            })
        
        # Sort by latest version created_at (most recent first)
        enriched_specs.sort(
            key=lambda x: x['latest_version_created_at'] if x['latest_version_created_at'] else '', 
            reverse=True
        )
        
        logger.info(f"Returning {len(enriched_specs)} enriched specs for tenant {tenant_id}")
        return enriched_specs

# -----------------------------------------------------------------------------
#  MUST COME LAST — dynamic path
# -----------------------------------------------------------------------------

@router.get("/{spec_id}", response_model=ApiSpecOut)
async def get_api_spec(
    spec_id: UUID,
    tenant_id: str = Depends(get_current_tenant_id),
    db: Session = Depends(get_db),
):
    with tracer.start_as_current_span("api.get_api_spec") as span:
        span.set_attribute("tenant.id", tenant_id)
        span.set_attribute("api_spec.id", spec_id)

        spec = (
            db.query(ApiSpec)
            .filter(
                ApiSpec.id == spec_id,
                ApiSpec.tenant_id == tenant_id,
            )
            .first()
        )

        if not spec:
            raise HTTPException(status_code=404, detail="API spec not found")

    return serialize_spec(spec)

@router.post("/{spec_id}/regenerate-docs")
async def regenerate_docs(
    spec_id: UUID,
    tenant_id: str = Depends(get_current_tenant_id),
    db: Session = Depends(get_db),
):
    """
    Trigger regeneration of Markdown + HTML documentation
    for a given API spec. Returns the S3 keys for the
    newly generated artifacts.
    """
    logger.info("Regenerating docs for spec_id=%s", spec_id)

    with tracer.start_as_current_span("api_specs.regenerate_docs") as span:
        span.set_attribute("spec.id", spec_id)
        span.set_attribute("tenant.id", tenant_id)

        spec = ApiSpecRepository.get_by_id(
            db=db,
            spec_id=spec_id,
            tenant_id=tenant_id,
        )

        if not spec:
            logger.warning(
                "Spec not found for regeneration spec_id=%s tenant_id=%s",
                spec_id,
                tenant_id,
            )
            raise HTTPException(status_code=404, detail="API spec not found")

        md_key, html_key = await regenerate_all_docs_for_spec(db, spec)

        if not md_key or not html_key:
            raise HTTPException(
                status_code=400,
                detail="Failed to regenerate documentation (missing or invalid schema)",
            )

        # keep the original response shape so tests/clients don't break
        return {
            "spec_id": spec.id,
            "markdown_s3_path": md_key,
            "html_s3_path": html_key,
        }
    
    from sqlalchemy import text

