# src/avanamy/services/original_spec_artifact_service.py

"""
Service for storing original OpenAPI spec file references in documentation_artifacts.

This allows us to retrieve the exact original spec for any version from S3,
enabling full schema diffs and comparisons.
"""

from __future__ import annotations
import logging
from uuid import UUID
from sqlalchemy.orm import Session
from opentelemetry import trace

from avanamy.repositories.documentation_artifact_repository import DocumentationArtifactRepository

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


def store_original_spec_artifact(
    db: Session,
    *,
    tenant_id: UUID,
    api_spec_id: UUID,
    version_history_id: int,
    s3_path: str,
) -> None:
    """
    Store a reference to the original spec file in documentation_artifacts.
    
    Args:
        db: Database session
        tenant_id: Tenant UUID
        api_spec_id: ApiSpec UUID
        version_history_id: VersionHistory ID for this version
        s3_path: S3 path where the original spec is stored
    """
    with tracer.start_as_current_span("service.store_original_spec_artifact") as span:
        span.set_attribute("spec.id", str(api_spec_id))
        span.set_attribute("version_history.id", version_history_id)
        
        logger.info(
            "Storing original spec artifact reference: spec_id=%s version_history_id=%s path=%s",
            api_spec_id,
            version_history_id,
            s3_path,
        )
        
        repo = DocumentationArtifactRepository()
        
        repo.create(
            db=db,
            tenant_id=str(tenant_id),
            api_spec_id=str(api_spec_id),
            artifact_type="original_spec",
            s3_path=s3_path,
            version_history_id=version_history_id,
        )
        
        logger.info(
            "Stored original spec artifact reference: spec_id=%s version_history_id=%s",
            api_spec_id,
            version_history_id,
        )