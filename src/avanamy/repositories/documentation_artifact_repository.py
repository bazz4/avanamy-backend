# src/avanamy/repositories/documentation_artifact_repository.py

from sqlalchemy.orm import Session
from avanamy.models.documentation_artifact import DocumentationArtifact
import logging
from opentelemetry import trace

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


class DocumentationArtifactRepository:

    @staticmethod
    def create(
        db: Session,
        *,
        tenant_id: str,
        api_spec_id: str,
        artifact_type: str,
        s3_path: str,
    ) -> DocumentationArtifact:

        artifact = DocumentationArtifact(
            tenant_id=tenant_id,
            api_spec_id=api_spec_id,
            artifact_type=artifact_type,
            s3_path=s3_path,
        )

        with tracer.start_as_current_span("db.create_documentation_artifact"):
            db.add(artifact)
            db.commit()
            db.refresh(artifact)

        logger.info(
            "Created documentation artifact id=%s for spec=%s tenant=%s",
            artifact.id,
            api_spec_id,
            tenant_id,
        )
        return artifact

    @staticmethod
    def get_latest(
        db: Session,
        *,
        api_spec_id: str,
        tenant_id: str,
        artifact_type: str,
    ) -> DocumentationArtifact | None:

        return (
            db.query(DocumentationArtifact)
            .filter(
                DocumentationArtifact.api_spec_id == api_spec_id,
                DocumentationArtifact.tenant_id == tenant_id,
                DocumentationArtifact.artifact_type == artifact_type,
            )
            .order_by(DocumentationArtifact.created_at.desc())
            .first()
        )

    @staticmethod
    def list_for_spec(db: Session, api_spec_id: str, tenant_id: str):
        return (
            db.query(DocumentationArtifact)
            .filter(
                DocumentationArtifact.api_spec_id == api_spec_id,
                DocumentationArtifact.tenant_id == tenant_id,
            )
            .order_by(DocumentationArtifact.created_at.desc())
            .all()
        )
