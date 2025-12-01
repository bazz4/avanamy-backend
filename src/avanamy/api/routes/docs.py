from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse, PlainTextResponse
from sqlalchemy.orm import Session

from avanamy.db.database import SessionLocal
from avanamy.repositories.api_spec_repository import ApiSpecRepository
from avanamy.repositories.documentation_artifact_repository import DocumentationArtifactRepository
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


@router.get("/{spec_id}")
def get_docs(spec_id: int, db: Session = Depends(get_db)):
    """
    Order:
    1. Use Markdown artifact if available (tests expect this)
    2. Otherwise serve HTML if available
    """
    artifact_repo = DocumentationArtifactRepository()
    artifact = artifact_repo.get_latest_by_spec_id(
        db,
        api_spec_id=spec_id,
        artifact_type=ARTIFACT_TYPE_API_MARKDOWN
    )

    if artifact:
        # Return markdown
        md_bytes = download_bytes(artifact.s3_path)
        return PlainTextResponse(
            md_bytes.decode("utf-8"),
            media_type="text/markdown"
        )

    # Fallback: try HTML
    spec = ApiSpecRepository().get_by_id(db, spec_id)
    if spec and spec.documentation_html_s3_path:
        html_bytes = download_bytes(spec.documentation_html_s3_path)
        return HTMLResponse(
            content=html_bytes.decode("utf-8"),
            media_type="text/html"
        )

    raise HTTPException(status_code=404, detail="Documentation not found")
