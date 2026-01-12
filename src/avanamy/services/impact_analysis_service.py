# src/avanamy/services/impact_analysis_service.py

"""
Impact Analysis Service

Analyzes how API spec changes impact code repositories.
Automatically runs when breaking changes are detected.
"""

from __future__ import annotations
import logging
import re
from typing import Dict, Any, List
from uuid import UUID
from datetime import datetime, timezone

from sqlalchemy.orm import Session
from opentelemetry import trace
from prometheus_client import Counter, Histogram

from avanamy.models.impact_analysis import ImpactAnalysisResult, AffectedCodeUsage
from avanamy.models.code_repository import CodeRepoEndpointUsage, CodeRepository

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)

# Prometheus metrics
impact_analyses_total = Counter(
    'impact_analyses_total',
    'Total number of impact analyses run',
    ['has_impact', 'severity']
)

impact_analysis_duration_seconds = Histogram(
    'impact_analysis_duration_seconds',
    'Time taken to run impact analysis',
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0]
)

affected_repositories_total = Counter(
    'affected_repositories_total',
    'Total repositories affected by breaking changes',
    ['severity']
)

affected_usages_total = Counter(
    'affected_usages_total',
    'Total code usages affected by breaking changes',
    ['breaking_change_type']
)

# System user constant for automated actions
SYSTEM_USER_ID = "system"


class ImpactAnalysisService:
    """
    Service for analyzing the impact of API changes on code repositories.
    """
    
    def __init__(self, db: Session):
        """
        Initialize impact analysis service.
        
        Args:
            db: Database session
        """
        self.db = db
    
    async def analyze_breaking_changes(
        self,
        tenant_id: str,
        diff: Dict[str, Any],
        spec_id: UUID,
        version_history_id: int,
        created_by_user_id: str | None = None,
    ) -> ImpactAnalysisResult:
        """
        Analyze which code repositories are affected by breaking changes.
        
        Args:
            tenant_id: Tenant ID
            diff: Diff object from spec_diff_engine
            spec_id: API spec ID
            version_history_id: Version history ID
            created_by_user_id: User who triggered analysis (None = system)
            
        Returns:
            ImpactAnalysisResult with all affected repositories and usages
        """
        with tracer.start_as_current_span("impact_analysis.analyze") as span:
            start_time = datetime.now(timezone.utc)
            
            span.set_attribute("tenant_id", tenant_id)
            span.set_attribute("spec_id", str(spec_id))
            span.set_attribute("version_history_id", version_history_id)
            
            user_id = created_by_user_id or SYSTEM_USER_ID
            
            logger.info(
                "Starting impact analysis: tenant=%s spec=%s version=%s created_by=%s",
                tenant_id,
                spec_id,
                version_history_id,
                user_id,
            )
            
            # Extract breaking changes from diff
            changes = diff.get("changes", [])
            breaking_changes = [
                c for c in changes
                if c["type"] in {
                    "endpoint_removed",
                    "method_removed",
                    "required_request_field_added",
                    "required_response_field_removed",
                }
            ]
            
            span.set_attribute("breaking_changes_count", len(breaking_changes))
            
            if not breaking_changes:
                logger.info("No breaking changes detected, creating empty impact analysis")
                return self._create_empty_result(
                    tenant_id=tenant_id,
                    spec_id=spec_id,
                    version_history_id=version_history_id,
                    user_id=user_id,
                )
            
            # Analyze each breaking change
            all_affected_usages = []
            repos_affected = set()
            
            for change in breaking_changes:
                with tracer.start_as_current_span("impact_analysis.analyze_change") as change_span:
                    change_type = change["type"]
                    change_span.set_attribute("change_type", change_type)
                    
                    affected_usages = await self._find_affected_usages(
                        tenant_id=tenant_id,
                        change=change,
                        user_id=user_id,
                    )
                    
                    all_affected_usages.extend(affected_usages)

                    # Track unique repos by repository name
                    for usage in affected_usages:
                        repos_affected.add(usage.repository_name)
                    
                    # Metrics per change type
                    affected_usages_total.labels(
                        breaking_change_type=change_type
                    ).inc(len(affected_usages))
                    
                    logger.info(
                        "Breaking change %s affects %d code usages",
                        change_type,
                        len(affected_usages),
                    )
            
            # Calculate overall severity
            severity = self._calculate_overall_severity(breaking_changes)
            
            # Create impact analysis result
            has_impact = len(all_affected_usages) > 0
            
            result = ImpactAnalysisResult(
                tenant_id=tenant_id,
                spec_id=spec_id,
                version_history_id=version_history_id,
                analyzed_at=datetime.now(timezone.utc),
                has_impact=has_impact,
                total_breaking_changes=len(breaking_changes),
                total_affected_repos=len(repos_affected),
                total_usages_affected=len(all_affected_usages),
                severity=severity,
                created_by_user_id=user_id,
                updated_by_user_id=user_id,
            )
            
            self.db.add(result)
            self.db.flush()  # Get the ID without committing
            
            # Add affected usages
            for affected_usage in all_affected_usages:
                affected_usage.impact_analysis_result_id = result.id
                self.db.add(affected_usage)
            
            self.db.commit()
            self.db.refresh(result)
            
            # Record metrics
            duration = (datetime.now(timezone.utc) - start_time).total_seconds()
            impact_analysis_duration_seconds.observe(duration)
            impact_analyses_total.labels(
                has_impact=str(has_impact),
                severity=severity
            ).inc()
            
            if has_impact:
                affected_repositories_total.labels(severity=severity).inc(len(repos_affected))
            
            span.set_attribute("has_impact", has_impact)
            span.set_attribute("total_affected_repos", len(repos_affected))
            span.set_attribute("total_usages", len(all_affected_usages))
            span.set_attribute("severity", severity)
            span.set_attribute("duration_seconds", duration)
            
            logger.info(
                "Impact analysis complete: has_impact=%s repos=%d usages=%d severity=%s duration=%.2fs created_by=%s",
                has_impact,
                len(repos_affected),
                len(all_affected_usages),
                severity,
                duration,
                user_id,
            )
            
            return result
    
    async def _find_affected_usages(
        self,
        tenant_id: str,
        change: Dict[str, Any],
        user_id: str,
    ) -> List[AffectedCodeUsage]:
        """
        Find code usages affected by a single breaking change.
        
        Args:
            tenant_id: Tenant ID
            change: Breaking change object from diff
            user_id: User ID for audit trail
            
        Returns:
            List of AffectedCodeUsage objects (not yet saved to DB)
        """
        with tracer.start_as_current_span("impact_analysis.find_usages") as span:
            change_type = change["type"]
            endpoint_path = change.get("path")
            http_method = change.get("method")
            
            span.set_attribute("change_type", change_type)
            span.set_attribute("endpoint_path", endpoint_path or "")
            span.set_attribute("http_method", http_method or "")
            
            if not endpoint_path:
                logger.warning("Breaking change missing endpoint path: %s", change)
                return []
            
            # Query all endpoint usages for this tenant
            query = self.db.query(CodeRepoEndpointUsage).join(
                CodeRepository
            ).filter(
                CodeRepoEndpointUsage.tenant_id == tenant_id
            )
            
            all_usages = query.all()
            
            span.set_attribute("total_usages_checked", len(all_usages))
            
            # Find matching usages (with path parameter matching)
            matching_usages = []
            for usage in all_usages:
                if self._paths_match(endpoint_path, usage.endpoint_path):
                    # If method specified in change, must match
                    if http_method and usage.http_method != http_method:
                        continue
                    matching_usages.append(usage)
            
            span.set_attribute("matching_usages_found", len(matching_usages))
            
            logger.debug(
                "Found %d matching usages for %s %s (checked %d total)",
                len(matching_usages),
                http_method or "ANY",
                endpoint_path,
                len(all_usages),
            )
            
            # Convert to AffectedCodeUsage objects
            severity = self._calculate_change_severity(change_type)
            affected_usages = []
            
            for usage in matching_usages:
                now = datetime.now(timezone.utc)

                affected_usage = AffectedCodeUsage(
                    tenant_id=tenant_id,
                    code_repo_endpoint_usage_id=usage.id,
                    breaking_change_type=change_type,
                    endpoint_path=endpoint_path,
                    http_method=http_method,
                    severity=severity,
                    # Denormalized fields for historical context
                    file_path=usage.file_path,
                    line_number=usage.line_number,
                    code_context=usage.code_context or "",
                    repository_name=usage.code_repository.name,
                    repository_url=usage.code_repository.url,
                    created_at=now,
                    updated_at=now,
                    created_by_user_id=user_id,
                    updated_by_user_id=user_id,
                )
                affected_usages.append(affected_usage)
            
            return affected_usages
    
    def _paths_match(self, spec_path: str, code_path: str) -> bool:
        """
        Check if spec path matches code path.
        
        Handles path parameters:
        - /users/{id} matches /users/123
        - /users/{id} matches /users/${userId}
        - /users matches /users (exact)
        
        Args:
            spec_path: Path from API spec (e.g., /users/{id})
            code_path: Path from code (e.g., /users/123 or /users/${id})
            
        Returns:
            True if paths match
        """
        # Remove query strings
        spec_path_clean = spec_path.split('?')[0]
        code_path_clean = code_path.split('?')[0]
        
        # Exact match
        if spec_path_clean == code_path_clean:
            return True
        
        # Convert spec path with {params} to regex pattern
        # /users/{id}/posts/{postId} -> ^/users/[^/]+/posts/[^/]+$
        pattern = re.escape(spec_path_clean)
        pattern = re.sub(r'\\{[^}]+\\}', r'[^/]+', pattern)
        pattern = f'^{pattern}$'
        
        try:
            return bool(re.match(pattern, code_path_clean))
        except re.error as e:
            logger.warning("Invalid regex pattern %s: %s", pattern, e)
            return False
    
    def _calculate_change_severity(self, change_type: str) -> str:
        """
        Calculate severity for a breaking change type.
        
        Args:
            change_type: Type of breaking change
            
        Returns:
            Severity level: "critical", "high", "medium", "low"
        """
        severity_map = {
            "endpoint_removed": "critical",
            "method_removed": "critical",
            "required_request_field_added": "high",
            "required_response_field_removed": "high",
        }
        return severity_map.get(change_type, "medium")
    
    def _calculate_overall_severity(self, breaking_changes: List[Dict[str, Any]]) -> str:
        """
        Calculate overall severity across all breaking changes.
        
        Takes the highest severity level found.
        
        Args:
            breaking_changes: List of breaking change objects
            
        Returns:
            Overall severity: "critical", "high", "medium", "low"
        """
        severity_levels = ["low", "medium", "high", "critical"]
        
        max_severity = "low"
        for change in breaking_changes:
            change_severity = self._calculate_change_severity(change["type"])
            if severity_levels.index(change_severity) > severity_levels.index(max_severity):
                max_severity = change_severity
        
        return max_severity
    
    def _create_empty_result(
        self,
        tenant_id: str,
        spec_id: UUID,
        version_history_id: int,
        user_id: str,
    ) -> ImpactAnalysisResult:
        """
        Create an empty impact analysis result (no breaking changes).
        
        Args:
            tenant_id: Tenant ID
            spec_id: API spec ID
            version_history_id: Version history ID
            user_id: User ID for audit trail
            
        Returns:
            ImpactAnalysisResult with has_impact=False
        """
        result = ImpactAnalysisResult(
            tenant_id=tenant_id,
            spec_id=spec_id,
            version_history_id=version_history_id,
            analyzed_at=datetime.now(timezone.utc),
            has_impact=False,
            total_breaking_changes=0,
            total_affected_repos=0,
            total_usages_affected=0,
            severity="low",
            created_by_user_id=user_id,
            updated_by_user_id=user_id,
        )
        
        self.db.add(result)
        self.db.commit()
        self.db.refresh(result)
        
        # Record metric
        impact_analyses_total.labels(
            has_impact="False",
            severity="low"
        ).inc()
        
        logger.info(
            "Created empty impact analysis: spec=%s version=%s created_by=%s",
            spec_id,
            version_history_id,
            user_id,
        )
        
        return result
