# src/avanamy/services/code_repo_scanner_service.py

"""
Code Repository Scanner Service

Orchestrates scanning code repositories for API endpoint usage.
"""

from __future__ import annotations
import logging
import os
from datetime import datetime, timezone
from uuid import UUID
from sqlalchemy.orm import Session
from opentelemetry import trace

from avanamy.services.code_scanner import CodeScanner, RegexScanner
from avanamy.models.code_repository import CodeRepository, CodeRepoEndpointUsage

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


class CodeRepoScannerService:
    """
    Service for scanning code repositories to find API endpoint usage.
    """
    
    def __init__(self, db: Session, scanner: CodeScanner | None = None):
        """
        Initialize scanner service.
        
        Args:
            db: Database session
            scanner: Code scanner implementation (defaults to RegexScanner)
        """
        self.db = db
        self.scanner = scanner or RegexScanner()
    
    async def scan_repository(
        self,
        code_repository_id: UUID,
        repo_path: str,
        commit_sha: str
    ) -> dict:
        """
        Scan a code repository for API endpoint usage.
        
        Args:
            code_repository_id: CodeRepository UUID
            repo_path: Path to cloned repository on disk
            commit_sha: Current commit SHA
            
        Returns:
            Scan results summary
        """
        with tracer.start_as_current_span("service.scan_code_repository") as span:
            span.set_attribute("code_repository.id", str(code_repository_id))
            span.set_attribute("commit.sha", commit_sha)
            
            # Get code repository record
            code_repository = self.db.query(CodeRepository).filter(
                CodeRepository.id == code_repository_id
            ).first()
            
            if not code_repository:
                raise ValueError(f"CodeRepository {code_repository_id} not found")
            
            # Update status
            code_repository.scan_status = "scanning"
            code_repository.last_scan_commit_sha = commit_sha
            self.db.commit()
            
            try:
                # Clear old usage records for this repo
                self.db.query(CodeRepoEndpointUsage).filter(
                    CodeRepoEndpointUsage.code_repository_id == code_repository_id
                ).delete()
                self.db.commit()
                
                # Scan all files
                all_matches = []
                files_scanned = 0
                
                for root, dirs, files in os.walk(repo_path):
                    # Skip common non-code directories
                    dirs[:] = [d for d in dirs if d not in {
                        '.git', 'node_modules', '__pycache__', 'venv', 'env',
                        '.next', 'dist', 'build', 'coverage', '.pytest_cache',
                        'target', 'bin', 'obj'  # Java/C# build dirs
                    }]
                    
                    for filename in files:
                        file_path = os.path.join(root, filename)
                        relative_path = os.path.relpath(file_path, repo_path)
                        
                        # Check if scanner supports this file
                        file_ext = os.path.splitext(filename)[1].lower()
                        if not self.scanner.supports_language(file_ext):
                            continue
                        
                        # Read and scan file
                        try:
                            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                                content = f.read()
                            
                            matches = self.scanner.scan_file(relative_path, content)
                            all_matches.extend(matches)
                            files_scanned += 1
                            
                        except Exception as e:
                            logger.warning(f"Failed to scan {relative_path}: {e}")
                            continue
                
                # Store matches in database
                for match in all_matches:
                    usage = CodeRepoEndpointUsage(
                        code_repository_id=code_repository_id,
                        tenant_id=code_repository.tenant_id,
                        endpoint_path=match.endpoint_path,
                        http_method=match.http_method,
                        file_path=match.file_path,
                        line_number=match.line_number,
                        code_context=match.code_context,
                        detection_method=match.detection_method,
                        confidence=match.confidence,
                        commit_sha=commit_sha
                    )
                    self.db.add(usage)
                
                # Update code repository stats
                code_repository.scan_status = "success"
                code_repository.last_scanned_at = datetime.now(timezone.utc)
                code_repository.total_files_scanned = files_scanned
                code_repository.total_endpoints_found = len(all_matches)
                code_repository.last_scan_error = None
                
                self.db.commit()
                
                span.set_attribute("scan.files_scanned", files_scanned)
                span.set_attribute("scan.endpoints_found", len(all_matches))
                
                logger.info(
                    f"Scan complete: code_repository={code_repository_id} "
                    f"files={files_scanned} endpoints={len(all_matches)}"
                )
                
                return {
                    "code_repository_id": str(code_repository_id),
                    "files_scanned": files_scanned,
                    "endpoints_found": len(all_matches),
                    "commit_sha": commit_sha,
                    "status": "success"
                }
                
            except Exception as e:
                # Update code repository with error
                code_repository.scan_status = "failed"
                code_repository.last_scan_error = str(e)
                self.db.commit()
                
                logger.exception(f"Scan failed for code_repository {code_repository_id}")
                span.set_attribute("scan.error", str(e))
                
                raise
    
    def find_affected_repositories(
        self,
        tenant_id: str,
        endpoint_path: str,
        http_method: str | None = None
    ) -> list[dict]:
        """
        Find code repositories that use a specific API endpoint.
        
        This powers impact analysis.
        
        Args:
            tenant_id: Tenant ID
            endpoint_path: API endpoint path (e.g., "/v1/users")
            http_method: Optional HTTP method filter
            
        Returns:
            List of affected code repositories with usage details
        """
        with tracer.start_as_current_span("service.find_affected_code_repositories"):
            query = self.db.query(CodeRepoEndpointUsage).filter(
                CodeRepoEndpointUsage.tenant_id == tenant_id,
                CodeRepoEndpointUsage.endpoint_path == endpoint_path
            )
            
            if http_method:
                query = query.filter(CodeRepoEndpointUsage.http_method == http_method)
            
            usages = query.all()
            
            # Group by code repository
            repos_map = {}
            for usage in usages:
                repo_id = str(usage.code_repository_id)
                if repo_id not in repos_map:
                    repos_map[repo_id] = {
                        "code_repository_id": repo_id,
                        "code_repository_name": usage.code_repository.name,
                        "owner_team": usage.code_repository.owner_team,
                        "owner_email": usage.code_repository.owner_email,
                        "usages": []
                    }
                
                repos_map[repo_id]["usages"].append({
                    "file_path": usage.file_path,
                    "line_number": usage.line_number,
                    "code_context": usage.code_context,
                    "http_method": usage.http_method,
                    "confidence": usage.confidence
                })
            
            result = list(repos_map.values())
            
            logger.info(
                f"Found {len(result)} code repositories affected by {endpoint_path}"
            )
            
            return result