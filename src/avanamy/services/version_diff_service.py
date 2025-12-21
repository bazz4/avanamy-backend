# src/avanamy/services/version_diff_service.py

"""
Version Diff Service

Handles computation and storage of diffs between consecutive spec versions.
Diffs are stored in VersionHistory.diff column.
"""

from __future__ import annotations
import json
import logging
from uuid import UUID
from sqlalchemy.orm import Session
from opentelemetry import trace

from avanamy.services.spec_diff_engine import diff_normalized_specs
from avanamy.services.s3 import download_bytes
from avanamy.repositories.version_history_repository import VersionHistoryRepository
from avanamy.repositories.documentation_artifact_repository import DocumentationArtifactRepository

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


def compute_and_store_diff(
    db: Session,
    *,
    spec_id: UUID,
    tenant_id: UUID,
    current_version: int,
    new_normalized_spec: dict,
) -> None:
    """
    Compute diff between current version and previous version, then store in VersionHistory.
    
    For version 1, no diff is computed (diff=None).
    For version 2+, diff is computed against previous version.
    
    Args:
        db: Database session
        spec_id: ApiSpec UUID
        tenant_id: Tenant UUID
        current_version: Current version number (the one we just created)
        new_normalized_spec: Normalized spec for current version
    """
    with tracer.start_as_current_span("service.compute_and_store_diff") as span:
        span.set_attribute("spec.id", str(spec_id))
        span.set_attribute("version", current_version)
        
        # Version 1 has no diff
        if current_version == 1:
            logger.info("Version 1 - no diff to compute for spec_id=%s", spec_id)
            span.set_attribute("diff.computed", False)
            return
        
        # Get previous version number
        previous_version = current_version - 1
        
        logger.info(
            "Computing diff for spec_id=%s: v%d -> v%d",
            spec_id,
            previous_version,
            current_version,
        )
        
        # Load previous normalized spec from S3
        try:
            previous_normalized_spec = _load_normalized_spec_for_version(
                db,
                spec_id=spec_id,
                tenant_id=tenant_id,
                version=previous_version,
            )
        except Exception:
            logger.exception(
                "Failed to load previous normalized spec for spec_id=%s version=%d",
                spec_id,
                previous_version,
            )
            span.set_attribute("diff.error", "failed_to_load_previous_spec")
            return
        
        if not previous_normalized_spec:
            logger.warning(
                "No previous normalized spec found for spec_id=%s version=%d",
                spec_id,
                previous_version,
            )
            span.set_attribute("diff.error", "previous_spec_not_found")
            return
        
        # Compute diff
        try:
            diff_result = diff_normalized_specs(
                old_spec=previous_normalized_spec,
                new_spec=new_normalized_spec,
            )
        except Exception:
            logger.exception(
                "Failed to compute diff for spec_id=%s v%d -> v%d",
                spec_id,
                previous_version,
                current_version,
            )
            span.set_attribute("diff.error", "diff_computation_failed")
            return
        
        # Store diff in VersionHistory
        try:
            version_history = VersionHistoryRepository.get_by_spec_and_version(
                db,
                api_spec_id=spec_id,
                version=current_version,
            )
            
            if not version_history:
                logger.error(
                    "VersionHistory not found for spec_id=%s version=%d",
                    spec_id,
                    current_version,
                )
                span.set_attribute("diff.error", "version_history_not_found")
                return
            
            # Update diff column
            version_history.diff = diff_result
            db.commit()
            
            span.set_attribute("diff.computed", True)
            span.set_attribute("diff.breaking", diff_result.get("breaking", False))
            span.set_attribute("diff.changes_count", len(diff_result.get("changes", [])))
            
            logger.info(
                "Stored diff for spec_id=%s version=%d: breaking=%s, changes=%d",
                spec_id,
                current_version,
                diff_result.get("breaking"),
                len(diff_result.get("changes", [])),
            )
            
        except Exception:
            logger.exception(
                "Failed to store diff in VersionHistory for spec_id=%s version=%d",
                spec_id,
                current_version,
            )
            span.set_attribute("diff.error", "storage_failed")


def _load_normalized_spec_for_version(
    db: Session,
    *,
    spec_id: UUID,
    tenant_id: UUID,
    version: int,
) -> dict | None:
    """
    Load normalized spec from S3 for a specific version.
    
    Strategy:
    Get all normalized_spec artifacts for this spec (ordered by created_at desc),
    then pick the one corresponding to the requested version.
    
    Since we create artifacts sequentially:
    - Latest artifact = current version
    - Second-to-last = previous version
    - etc.
    
    Args:
        db: Database session
        spec_id: ApiSpec UUID
        tenant_id: Tenant UUID
        version: Version number
        
    Returns:
        Normalized spec dict or None if not found
    """
    # Get all normalized_spec artifacts for this spec
    all_artifacts = DocumentationArtifactRepository.list_for_spec(
        db,
        api_spec_id=str(spec_id),
        tenant_id=str(tenant_id),
    )
    
    # Filter to only normalized_spec type
    normalized_artifacts = [
        a for a in all_artifacts 
        if a.artifact_type == "normalized_spec"
    ]
    
    if not normalized_artifacts:
        logger.warning(
            "No normalized_spec artifacts found for spec_id=%s",
            spec_id,
        )
        return None
    
    # Artifacts are ordered by created_at desc (newest first)
    # Map: index 0 = latest version, index 1 = previous, etc.
    current_version = len(normalized_artifacts)  # Total versions
    artifact_index = current_version - version  # 0-based index
    
    if artifact_index < 0 or artifact_index >= len(normalized_artifacts):
        logger.warning(
            "Version %d out of range for spec_id=%s (have %d versions)",
            version,
            spec_id,
            current_version,
        )
        return None
    
    artifact = normalized_artifacts[artifact_index]
    
    logger.info(
        "Loading normalized spec for version=%d from S3: %s",
        version,
        artifact.s3_path,
    )
    
    # Download from S3
    try:
        normalized_bytes = download_bytes(artifact.s3_path)
        normalized_json = normalized_bytes.decode("utf-8")
        normalized_spec = json.loads(normalized_json)
        return normalized_spec
    except Exception:
        logger.exception(
            "Failed to download/parse normalized spec from S3: %s",
            artifact.s3_path,
        )
        return None