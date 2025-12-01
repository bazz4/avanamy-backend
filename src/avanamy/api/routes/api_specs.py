from __future__ import annotations

import json
import logging
from opentelemetry import trace

from typing import List, Optional, Dict, Any

from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from avanamy.db.database import SessionLocal
from avanamy.models.api_spec import ApiSpec
from avanamy.repositories.api_spec_repository import ApiSpecRepository
from avanamy.services.api_spec_service import store_api_spec_file
from avanamy.services.documentation_service import regenerate_all_docs_for_spec


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
    id: int
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
    name: Optional[str] = None,
    version: Optional[str] = None,
    description: Optional[str] = None,
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
            name=name,
            version=version,
            description=description,
            parsed_schema=None,
        )

    logger.info("API upload handler complete: spec_id=%s filename=%s", getattr(spec, "id", None), getattr(spec, "name", None))
    return serialize_spec(spec)


@router.get("/", response_model=List[ApiSpecOut])
def list_api_specs(db: Session = Depends(get_db)):
    """
    List all API specs.
    """
    return [serialize_spec(s) for s in ApiSpecRepository.list_all(db)]

@router.post("/{spec_id}/regenerate-docs")
def regenerate_docs(spec_id: int, db: Session = Depends(get_db)):
    """
    Regenerates markdown + HTML documentation for the given spec.
    """
    logger.info("API request: regenerate docs for spec_id=%s", spec_id)

    with tracer.start_as_current_span("api.regenerate_docs") as span:
        span.set_attribute("spec.id", spec_id)

        spec = ApiSpecRepository.get_by_id(db, spec_id)
        if not spec:
            raise HTTPException(status_code=404, detail="API spec not found")

        md_key, html_key = regenerate_all_docs_for_spec(db, spec)

        if not md_key or not html_key:
            raise HTTPException(
                status_code=400,
                detail="Failed to regenerate documentation (missing or invalid schema)",
            )

        return {
            "spec_id": spec.id,
            "markdown_s3_path": md_key,
            "html_s3_path": html_key,
        }

# -----------------------------------------------------------------------------
#  MUST COME LAST — dynamic path
# -----------------------------------------------------------------------------

@router.get("/{spec_id}", response_model=ApiSpecOut)
def get_api_spec(spec_id: int, db: Session = Depends(get_db)):
    """
    Get a single API spec by ID.
    """
    spec = ApiSpecRepository.get_by_id(db, spec_id)
    if not spec:
        raise HTTPException(status_code=404, detail="API spec not found")
    return serialize_spec(spec)

@router.post("/{spec_id}/regenerate-docs")
def regenerate_docs(spec_id: int, db: Session = Depends(get_db)):
    """
    Trigger regeneration of Markdown + HTML documentation
    for a given API spec. Returns the S3 keys for the
    newly generated artifacts.
    """
    logger.info("Regenerating docs for spec_id=%s", spec_id)

    with tracer.start_as_current_span("api_specs.regenerate_docs") as span:
        span.set_attribute("spec.id", spec_id)

        spec = db.query(ApiSpec).filter(ApiSpec.id == spec_id).first()
        if not spec:
            logger.warning("Spec not found for regeneration spec_id=%s", spec_id)
            raise HTTPException(status_code=404, detail="API spec not found")

        md_key, html_key = regenerate_all_docs_for_spec(db, spec)

        # keep response simple for now; we can extend with more metadata later
        return {
            "markdown_key": md_key,
            "html_key": html_key,
        }