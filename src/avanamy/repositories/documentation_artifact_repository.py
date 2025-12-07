# src/avanamy/repositories/documentation_artifact_repository.py

from sqlalchemy.orm import Session
from avanamy.models.documentation_artifact import DocumentationArtifact
import logging
from opentelemetry import trace

from avanamy.services.s3 import upload_bytes

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


class DocumentationArtifactRepository:

    @staticmethod
    def create(
        db: Session,
        *,
        tenant_id: str,
        api_spec_id: int,
        artifact_type: str,
        s3_path: str,
    ) -> DocumentationArtifact:
        artifact = DocumentationArtifact(
            tenant_id=tenant_id,
            api_spec_id=api_spec_id,
            artifact_type=artifact_type,
            s3_path=s3_path,
        )

        with tracer.start_as_current_span("db.create_documentation_artifact") as span:
            span.set_attribute("tenant_id", tenant_id)
            span.set_attribute("api_spec_id", api_spec_id)
            span.set_attribute("artifact.type", artifact_type)
            db.add(artifact)
            db.commit()
            db.refresh(artifact)

        logger.info(
            "Created documentation artifact id=%s for spec=%s tenant=%s",
            getattr(artifact, "id", "?"),
            api_spec_id,
            tenant_id,
        )

        return artifact

    @staticmethod
    def get_latest_by_spec_id(
        db: Session,
        api_spec_id: int,
        tenant_id: str,
        artifact_type: str | None = None,
    ) -> DocumentationArtifact | None:

        with tracer.start_as_current_span("db.get_latest_documentation_artifact") as span:
            span.set_attribute("api_spec_id", api_spec_id)
            span.set_attribute("tenant_id", tenant_id)
            if artifact_type:
                span.set_attribute("artifact.type", artifact_type)

            query = (
                db.query(DocumentationArtifact)
                .filter(
                    DocumentationArtifact.api_spec_id == api_spec_id,
                    DocumentationArtifact.tenant_id == tenant_id,
                )
            )

            if artifact_type:
                query = query.filter(
                    DocumentationArtifact.artifact_type == artifact_type
                )

            result = query.order_by(
                DocumentationArtifact.created_at.desc()
            ).first()

        logger.debug(
            "Fetched latest artifact for spec=%s tenant=%s -> %s",
            api_spec_id,
            tenant_id,
            getattr(result, "id", None),
        )

        return result

    @staticmethod
    def list_for_spec(db: Session, api_spec_id: int, tenant_id: str):
        with tracer.start_as_current_span("db.list_documentation_artifacts") as span:
            span.set_attribute("api_spec_id", api_spec_id)
            span.set_attribute("tenant_id", tenant_id)

            results = (
                db.query(DocumentationArtifact)
                .filter(
                    DocumentationArtifact.api_spec_id == api_spec_id,
                    DocumentationArtifact.tenant_id == tenant_id,
                )
                .order_by(DocumentationArtifact.created_at.desc())
                .all()
            )

        logger.debug(
            "Listed %d artifacts for spec=%s tenant=%s",
            len(results),
            api_spec_id,
            tenant_id,
        )

        return results
    
    @staticmethod
    def store_markdown(db, tenant_id, api_spec_id, version_label, markdown: str):
        key = f"docs/{tenant_id}/{api_spec_id}/{version_label}/api.md"
        upload_bytes(key, markdown.encode("utf-8"))
        # save to DB
        artifact = DocumentationArtifact(
            api_spec_id=api_spec_id,
            artifact_type="markdown",
            s3_path=key,
        )
        db.add(artifact)
        db.commit()

    @staticmethod
    def store_html(db, tenant_id, api_spec_id, version_label, html: str):
        key = f"docs/{tenant_id}/{api_spec_id}/{version_label}/api.html"
        upload_bytes(key, html.encode("utf-8"))
        artifact = DocumentationArtifact(
            api_spec_id=api_spec_id,
            artifact_type="html",
            s3_path=key,
        )
        db.add(artifact)
        db.commit()

