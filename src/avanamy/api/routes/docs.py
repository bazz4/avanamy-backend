# src/avanamy/api/routes/docs.py

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from avanamy.db.database import SessionLocal
from avanamy.repositories.api_spec_repository import ApiSpecRepository
from avanamy.repositories.documentation_artifact_repository import DocumentationArtifactRepository

from avanamy.services.s3 import download_bytes

router = APIRouter(
    prefix="/docs",
    tags=["Documentation"],
)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get("/{spec_id}", response_class=PlainTextResponse)
def get_docs(spec_id: int, db: Session = Depends(get_db)):
    repo = DocumentationArtifactRepository()

    artifact = repo.get_latest_by_spec_id(
        db=db,
        api_spec_id=spec_id,
        artifact_type="api_markdown",
    )

    if not artifact:
        raise HTTPException(status_code=404, detail="Documentation not found")

    md_bytes = download_bytes(artifact.s3_path)
    return PlainTextResponse(content=md_bytes.decode("utf-8"), media_type="text/markdown")

