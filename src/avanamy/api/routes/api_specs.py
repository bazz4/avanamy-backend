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
from sqlalchemy.orm import Session

from avanamy.api.dependencies.tenant import get_tenant_id
from avanamy.db.database import SessionLocal
from avanamy.models.api_spec import ApiSpec
from avanamy.repositories.api_spec_repository import ApiSpecRepository
from avanamy.services.api_spec_service import store_api_spec_file, update_api_spec_file
from avanamy.services.documentation_service import regenerate_all_docs_for_spec
from avanamy.repositories.version_history_repository import VersionHistoryRepository
from avanamy.api.dependencies.tenant import get_tenant_id
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
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
):
    """
    Upload an API spec file and store in S3 + DB.
    """
    contents = await file.read()

    logger.info("API upload handler start: filename=%s", file.filename)
    with tracer.start_as_current_span("api.upload_api_spec") as span:
        span.set_attribute("file.size", len(contents) if contents is not None else 0)

    spec = store_api_spec_file(
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
    tenant_id: str = Depends(get_tenant_id),
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
    """
    contents = await file.read()
    tenant_uuid = UUID(tenant_id)

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
            tenant_id=tenant_uuid,
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
        updated_spec = update_api_spec_file(
            db=db,
            spec=spec,
            file_bytes=contents,
            filename=file.filename,
            content_type=file.content_type,
            tenant_id=tenant_id,
            version=effective_version,
            description=effective_description,
        )

    logger.info(
        "API new-version upload handler complete: spec_id=%s filename=%s",
        spec_id,
        getattr(updated_spec, "name", None),
    )

    return serialize_spec(updated_spec)

@router.get("/", response_model=List[ApiSpecOut])
def list_api_specs(
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
):
    with tracer.start_as_current_span("api.list_api_specs") as span:
        span.set_attribute("tenant.id", tenant_id)

        # Convert to UUID if your column is UUID
        tenant_uuid = UUID(tenant_id)

        specs = (
            db.query(ApiSpec)
            .filter(ApiSpec.tenant_id == tenant_uuid)
            .order_by(ApiSpec.created_at.desc())
            .all()
        )

    return [serialize_spec(s) for s in specs]

# -----------------------------------------------------------------------------
#  MUST COME LAST — dynamic path
# -----------------------------------------------------------------------------

@router.get("/{spec_id}", response_model=ApiSpecOut)
def get_api_spec(
    spec_id: UUID,
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
):
    tenant_uuid = UUID(tenant_id)

    with tracer.start_as_current_span("api.get_api_spec") as span:
        span.set_attribute("tenant.id", tenant_id)
        span.set_attribute("api_spec.id", spec_id)

        spec = (
            db.query(ApiSpec)
            .filter(
                ApiSpec.id == spec_id,
                ApiSpec.tenant_id == tenant_uuid,
            )
            .first()
        )

        if not spec:
            raise HTTPException(status_code=404, detail="API spec not found")

    return serialize_spec(spec)

@router.post("/{spec_id}/regenerate-docs")
def regenerate_docs(
    spec_id: UUID,
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
):
    """
    Trigger regeneration of Markdown + HTML documentation
    for a given API spec. Returns the S3 keys for the
    newly generated artifacts.
    """
    logger.info("Regenerating docs for spec_id=%s", spec_id)

    tenant_uuid = UUID(tenant_id)

    with tracer.start_as_current_span("api_specs.regenerate_docs") as span:
        span.set_attribute("spec.id", spec_id)
        span.set_attribute("tenant.id", tenant_id)

        spec = ApiSpecRepository.get_by_id(
            db=db,
            spec_id=spec_id,
            tenant_id=tenant_uuid,
        )

        if not spec:
            logger.warning(
                "Spec not found for regeneration spec_id=%s tenant_id=%s",
                spec_id,
                tenant_id,
            )
            raise HTTPException(status_code=404, detail="API spec not found")

        md_key, html_key = regenerate_all_docs_for_spec(db, spec)

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