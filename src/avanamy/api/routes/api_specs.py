# src/avanamy/api/routes/api_specs.py

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from avanamy.db.database import SessionLocal
from avanamy.repositories.api_spec_repository import ApiSpecRepository
from avanamy.services.api_spec_service import store_api_spec_file

router = APIRouter(
    prefix="/api-specs",
    tags=["API Specs"],
)


# --- DB dependency (local to this router) ------------------------------------ #

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# --- Pydantic response models ------------------------------------------------ #

class ApiSpecOut(BaseModel):
    id: int
    name: str
    version: Optional[str] = None
    description: Optional[str] = None
    original_file_s3_path: str

    class Config:
        from_attributes = True  # Pydantic v2 (allows ORM objects)


# --- Routes ------------------------------------------------------------------ #

@router.post("/upload", response_model=ApiSpecOut)
async def upload_api_spec(
    file: UploadFile = File(...),
    name: Optional[str] = None,
    version: Optional[str] = None,
    description: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """
    Upload an API spec file, store it in S3, and create a DB record.

    - Accepts a multipart/form-data file
    - Optional name/version/description override the defaults
    """
    contents = await file.read()

    # (Later) we can inspect content_type and parse OpenAPI/JSON/YAML here
    spec = store_api_spec_file(
        db=db,
        file_bytes=contents,
        filename=file.filename,
        content_type=file.content_type,
        name=name,
        version=version,
        description=description,
        parsed_schema=None,  # placeholder for future parsing
    )

    return spec


@router.get("/", response_model=List[ApiSpecOut])
def list_api_specs(db: Session = Depends(get_db)):
    """
    List all API specs.
    """
    return ApiSpecRepository.list_all(db)


@router.get("/{spec_id}", response_model=ApiSpecOut)
def get_api_spec(spec_id: int, db: Session = Depends(get_db)):
    """
    Get a single API spec by ID.
    """
    spec = ApiSpecRepository.get_by_id(db, spec_id)
    if not spec:
        raise HTTPException(status_code=404, detail="API spec not found")
    return spec
