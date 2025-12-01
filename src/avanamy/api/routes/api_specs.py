# src/avanamy/api/routes/api_specs.py

from __future__ import annotations
import json
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from avanamy.db.database import SessionLocal
from avanamy.repositories.api_spec_repository import ApiSpecRepository
from avanamy.services.api_spec_service import store_api_spec_file
import logging
from opentelemetry import trace

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
