# src/avanamy/api/routes/docs.py

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from avanamy.db.database import SessionLocal
from avanamy.repositories.documentation_artifact_repository import (
    DocumentationArtifactRepository,
)
from avanamy.services.s3 import download_bytes
from avanamy.services.documentation_service import ARTIFACT_TYPE_API_MARKDOWN


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
def get_documentation_for_spec(spec_id: int, db: Session = Depends(get_db)):
    """
    Return the generated Markdown documentation for a given API spec.
    """
    repo = DocumentationArtifactRepository()
    artifact = repo.get_latest_by_spec_id(
        db, api_spec_id=spec_id, artifact_type=ARTIFACT_TYPE_API_MARKDOWN
    )
    if not artifact:
        raise HTTPException(status_code=404, detail="Documentation not found")

    # s3_path here is assumed to be the key
    try:
        content = download_bytes(artifact.s3_path)
    except Exception:
        raise HTTPException(
            status_code=502,
            detail="Failed to retrieve documentation from storage",
        )

    if not content:
        raise HTTPException(status_code=404, detail="Documentation is empty")

    return PlainTextResponse(content.decode("utf-8"), media_type="text/markdown")
