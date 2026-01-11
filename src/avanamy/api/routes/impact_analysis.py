# src/avanamy/api/routes/impact_analysis.py

"""
Impact Analysis API Routes

Provides endpoints for viewing impact analysis results.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from pydantic import BaseModel
from uuid import UUID

from avanamy.db.database import get_db
from avanamy.auth.clerk import get_current_tenant_id
from avanamy.models.impact_analysis import ImpactAnalysisResult, AffectedCodeUsage
from avanamy.models.version_history import VersionHistory
import logging
from opentelemetry import trace

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)
router = APIRouter()


# Response Models
class AffectedUsageOut(BaseModel):
    file_path: str
    line_number: int
    code_context: str
    confidence: float
    repository_name: str
    repository_url: str | None

class AffectedRepositoryOut(BaseModel):
    repository_id: str
    repository_name: str
    repository_url: str | None
    usages_count: int
    usages: List[AffectedUsageOut]

class BreakingChangeOut(BaseModel):
    breaking_change_type: str
    endpoint_path: str
    http_method: str | None
    severity: str
    affected_repositories: List[AffectedRepositoryOut]

class ImpactAnalysisOut(BaseModel):
    has_impact: bool
    total_breaking_changes: int
    total_affected_repos: int
    total_usages_affected: int
    severity: str
    analyzed_at: str
    created_by_user_id: str | None
    breaking_changes: List[BreakingChangeOut]


@router.get("/version-history/{version_history_id}/impact", response_model=ImpactAnalysisOut)
def get_impact_analysis(
    version_history_id: int,
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_current_tenant_id),
):
    """
    Get impact analysis results for a version.
    
    Shows which code repositories are affected by breaking changes.
    """
    with tracer.start_as_current_span("api.get_impact_analysis") as span:
        span.set_attribute("tenant_id", tenant_id)
        span.set_attribute("version_history_id", version_history_id)
        
        # Verify version exists and belongs to tenant
        version = db.query(VersionHistory).filter(
            VersionHistory.id == version_history_id
        ).first()
        
        if not version:
            raise HTTPException(status_code=404, detail="Version not found")
        
        # Get impact analysis result
        impact_result = db.query(ImpactAnalysisResult).filter(
            ImpactAnalysisResult.version_history_id == version_history_id,
            ImpactAnalysisResult.tenant_id == tenant_id,
        ).first()
        
        if not impact_result:
            raise HTTPException(status_code=404, detail="Impact analysis not found")
        
        # Get all affected usages with relationships loaded
        affected_usages = db.query(AffectedCodeUsage).filter(
            AffectedCodeUsage.impact_analysis_result_id == impact_result.id
        ).all()
        
        # Group by breaking change type and repository
        breaking_changes_map = {}
        
        for usage in affected_usages:
            # Group by breaking change type + endpoint
            change_key = f"{usage.breaking_change_type}:{usage.endpoint_path}:{usage.http_method or 'ANY'}"
            
            if change_key not in breaking_changes_map:
                breaking_changes_map[change_key] = {
                    "breaking_change_type": usage.breaking_change_type,
                    "endpoint_path": usage.endpoint_path,
                    "http_method": usage.http_method,
                    "severity": usage.severity,
                    "repos": {}
                }
            
            # Group by repository within each change
            repo_id = str(usage.code_repo_endpoint_usage_id)  # Using usage ID as unique identifier
            repo_key = usage.repository_name
            
            if repo_key not in breaking_changes_map[change_key]["repos"]:
                breaking_changes_map[change_key]["repos"][repo_key] = {
                    "repository_id": repo_id,
                    "repository_name": usage.repository_name,
                    "repository_url": usage.repository_url,
                    "usages": []
                }
            
            breaking_changes_map[change_key]["repos"][repo_key]["usages"].append({
                "file_path": usage.file_path,
                "line_number": usage.line_number,
                "code_context": usage.code_context,
                "confidence": usage.code_usage.confidence if usage.code_usage else 0.0,
                "repository_name": usage.repository_name,
                "repository_url": usage.repository_url,
            })
        
        # Convert to output format
        breaking_changes = []
        for change in breaking_changes_map.values():
            repos_list = []
            for repo in change["repos"].values():
                repos_list.append({
                    "repository_id": repo["repository_id"],
                    "repository_name": repo["repository_name"],
                    "repository_url": repo["repository_url"],
                    "usages_count": len(repo["usages"]),
                    "usages": repo["usages"],
                })
            
            breaking_changes.append({
                "breaking_change_type": change["breaking_change_type"],
                "endpoint_path": change["endpoint_path"],
                "http_method": change["http_method"],
                "severity": change["severity"],
                "affected_repositories": repos_list,
            })
        
        span.set_attribute("impact.has_impact", impact_result.has_impact)
        span.set_attribute("impact.breaking_changes_count", len(breaking_changes))
        
        return {
            "has_impact": impact_result.has_impact,
            "total_breaking_changes": impact_result.total_breaking_changes,
            "total_affected_repos": impact_result.total_affected_repos,
            "total_usages_affected": impact_result.total_usages_affected,
            "severity": impact_result.severity,
            "analyzed_at": impact_result.analyzed_at.isoformat(),
            "created_by_user_id": impact_result.created_by_user_id,
            "breaking_changes": breaking_changes,
        }