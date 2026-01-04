# src/avanamy/services/normalized_spec_service.py

"""
Service for generating and storing normalized OpenAPI spec artifacts.

Normalized specs are stored as versioned S3 artifacts for:
- Diff computation
- Breaking change detection
- Future AI/embedding features
"""

from __future__ import annotations
import json
import logging
from uuid import UUID
from sqlalchemy.orm import Session
from opentelemetry import trace

from avanamy.services.spec_normalizer import normalize_openapi_spec
from avanamy.services.s3 import upload_bytes
from avanamy.repositories.documentation_artifact_repository import DocumentationArtifactRepository
from avanamy.utils.s3_paths import build_normalized_spec_path

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


def generate_and_store_normalized_spec(
    db: Session,
    *,
    tenant_slug: str,
    provider_slug: str,
    product_slug: str,
    version_label: str,
    spec_id: UUID,
    spec_slug: str,
    parsed_spec: dict,
    tenant_id: str,
) -> str:
    """
    Generate normalized spec and store as S3 artifact.
    
    Args:
        db: Database session
        tenant_slug: Tenant slug for S3 path
        provider_slug: Provider slug for S3 path
        product_slug: Product slug for S3 path
        version_label: Version label (e.g., "v1")
        spec_id: ApiSpec UUID
        spec_slug: Spec slug for filename
        parsed_spec: Parsed OpenAPI spec dict
        tenant_id: Tenant UUID for DB record
        
    Returns:
        S3 path of the stored normalized spec
    """
    with tracer.start_as_current_span("service.generate_normalized_spec") as span:
        span.set_attribute("spec.id", str(spec_id))
        span.set_attribute("version", version_label)
        
        # Generate normalized spec
        normalized_spec = normalize_openapi_spec(parsed_spec)
        
        # Convert to JSON
        normalized_json = json.dumps(normalized_spec, indent=2, sort_keys=True)
        
        # Build S3 path
        s3_path = build_normalized_spec_path(
            tenant_slug=tenant_slug,
            provider_slug=provider_slug,
            product_slug=product_slug,
            version=version_label,
            spec_id=spec_id,
            spec_slug=spec_slug,
        )
        
        logger.info(
            "Uploading normalized spec to S3: spec_id=%s version=%s path=%s",
            spec_id,
            version_label,
            s3_path,
        )
        
        # Upload to S3
        upload_bytes(
            s3_path,
            normalized_json.encode("utf-8"),
            content_type="application/json",
        )
        
        # Create artifact record
        repo = DocumentationArtifactRepository()
        
        # Get the version_history_id for this version
        from avanamy.models.version_history import VersionHistory
        version_history = db.query(VersionHistory).filter(
            VersionHistory.api_spec_id == spec_id
        ).order_by(VersionHistory.version.desc()).first()
        
        repo.create(
            db=db,
            tenant_id=str(tenant_id),
            api_spec_id=str(spec_id),
            artifact_type="normalized_spec",
            s3_path=s3_path,
            version_history_id=version_history.id if version_history else None,
        )

        logger.info(
            "Stored normalized spec artifact: spec_id=%s version=%s",
            spec_id,
            version_label,
        )
        
        return s3_path