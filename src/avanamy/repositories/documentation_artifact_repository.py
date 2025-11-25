# src/avanamy/repositories/documentation_artifact_repository.py

from sqlalchemy.orm import Session
from avanamy.models.documentation_artifact import DocumentationArtifact

class DocumentationArtifactRepository:

    @staticmethod
    def create(db: Session, *, api_spec_id: int,
               artifact_type: str, s3_path: str):

        artifact = DocumentationArtifact(
            api_spec_id=api_spec_id,
            artifact_type=artifact_type,
            s3_path=s3_path,
        )
        db.add(artifact)
        db.commit()
        db.refresh(artifact)
        return artifact

    @staticmethod
    def list_for_spec(db: Session, api_spec_id: int):
        return (
            db.query(DocumentationArtifact)
            .filter(DocumentationArtifact.api_spec_id == api_spec_id)
            .order_by(DocumentationArtifact.created_at.desc())
            .all()
        )
