# src/avanamy/services/version_diff_service.py

"""
Version Diff Service

Handles computation and storage of diffs between consecutive spec versions.
Diffs are stored in VersionHistory.diff column.
"""

from __future__ import annotations
import json
import logging
import asyncio
from uuid import UUID
from sqlalchemy.orm import Session
from opentelemetry import trace

from avanamy.models.documentation_artifact import DocumentationArtifact
from avanamy.services.spec_diff_engine import diff_normalized_specs
from avanamy.services.s3 import download_bytes
from avanamy.services.impact_analysis_service import ImpactAnalysisService
from avanamy.repositories.version_history_repository import VersionHistoryRepository
from avanamy.repositories.documentation_artifact_repository import DocumentationArtifactRepository

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


async def compute_and_store_diff(
    db: Session,
    *,
    spec_id: UUID,
    tenant_id: str,
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

            # ====================================================================
            # TRIGGER IMPACT ANALYSIS IF BREAKING CHANGES DETECTED
            # ====================================================================
            logger.info(
                "DEBUG: Checking breaking changes - diff_result.get('breaking', False) = %s",
                diff_result.get("breaking", False)
            )

            if diff_result.get("breaking", False):
                logger.info(
                    "Breaking changes detected in spec_id=%s version=%d version_history_id=%d, triggering impact analysis",
                    spec_id,
                    current_version,
                    version_history.id,
                )

                try:
                    logger.info("DEBUG: Creating ImpactAnalysisService instance")
                    impact_service = ImpactAnalysisService(db)

                    logger.info("DEBUG: Calling analyze_breaking_changes with version_history_id=%d", version_history.id)
                    impact_result = await impact_service.analyze_breaking_changes(
                        tenant_id=tenant_id,
                        diff=diff_result,
                        spec_id=spec_id,
                        version_history_id=version_history.id,
                        created_by_user_id=None,  # System-generated
                    )

                    logger.info(
                        "Impact analysis complete: has_impact=%s, affected_repos=%d, usages=%d",
                        impact_result.has_impact,
                        impact_result.total_affected_repos,
                        impact_result.total_usages_affected,
                    )

                    span.set_attribute("impact_analysis.has_impact", impact_result.has_impact)
                    span.set_attribute("impact_analysis.affected_repos", impact_result.total_affected_repos)
                    span.set_attribute("impact_analysis.usages_affected", impact_result.total_usages_affected)

                except Exception as e:
                    # Don't fail the diff storage if impact analysis fails
                    logger.error(
                        "Impact analysis failed for spec_id=%s version=%d: %s",
                        spec_id,
                        current_version,
                        str(e),
                        exc_info=True,
                    )
                    span.set_attribute("impact_analysis.error", str(e))
            else:
                logger.info(
                    "No breaking changes in spec_id=%s version=%d, skipping impact analysis",
                    spec_id,
                    current_version,
                )
            # ====================================================================
            # END IMPACT ANALYSIS TRIGGER
            # ====================================================================
            
            # Generate AI summary (best-effort, don't fail if it doesn't work)
            try:
                from avanamy.services.ai_summary_service import generate_diff_summary
                
                summary = generate_diff_summary(
                    diff=diff_result,
                    version_from=previous_version,
                    version_to=current_version,
                )
                
                if summary:
                    version_history.summary = summary
                    db.commit()
                    logger.info("Generated AI summary for spec_id=%s version=%d", spec_id, current_version)
                    span.set_attribute("summary.generated", True)
                else:
                    logger.info("No AI summary generated for spec_id=%s version=%d", spec_id, current_version)
                    span.set_attribute("summary.generated", False)
                    
            except Exception:
                logger.exception("Failed to generate AI summary for spec_id=%s version=%d", spec_id, current_version)
                span.set_attribute("summary.error", True)
                # Don't fail the whole operation if summary generation fails
            
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
    tenant_id: str,
    version: int,
) -> dict | None:
    """
    Load normalized spec from S3 for a specific version.
    
    Uses version_history_id to find the correct artifact, not artifact count.
    
    Args:
        db: Database session
        spec_id: ApiSpec UUID
        tenant_id: Tenant UUID
        version: Version number
        
    Returns:
        Normalized spec dict or None if not found
    """
    from avanamy.models.version_history import VersionHistory
    
    # Get the VersionHistory record for this version
    version_history = (
        db.query(VersionHistory)
        .filter(
            VersionHistory.api_spec_id == spec_id,
            VersionHistory.version == version,
        )
        .first()
    )
    
    if not version_history:
        logger.warning(
            "VersionHistory not found for spec_id=%s version=%d",
            spec_id,
            version,
        )
        return None
    
    # Get the normalized_spec artifact for this version_history_id
    artifact = (
        db.query(DocumentationArtifact)
        .filter(
            DocumentationArtifact.version_history_id == version_history.id,
            DocumentationArtifact.artifact_type == "normalized_spec",
        )
        .first()
    )
    
    if not artifact:
        logger.warning(
            "No normalized_spec artifact found for spec_id=%s version=%d (version_history_id=%d)",
            spec_id,
            version,
            version_history.id,
        )
        return None
    
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