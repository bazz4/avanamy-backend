# src/avanamy/api/routes/code_repositories.py

"""
Code Repository API endpoints.
"""

from __future__ import annotations
import logging
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from opentelemetry import trace

from avanamy.db.database import get_db
from avanamy.auth.clerk import get_current_tenant_id
from avanamy.repositories.code_repo_repository import CodeRepoRepository

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)
router = APIRouter(prefix="/code-repositories", tags=["code-repositories"])


# Request/Response Models
class CreateCodeRepositoryRequest(BaseModel):
    """Request to create a code repository."""
    name: str = Field(..., min_length=1, max_length=255)
    url: str = Field(..., min_length=1, max_length=500)
    owner_team: str | None = Field(None, max_length=255)
    owner_email: str | None = Field(None, max_length=255)
    access_token_encrypted: str | None = Field(None)
    installation_id: int | None = Field(None)


class UpdateCodeRepositoryRequest(BaseModel):
    """Request to update a code repository."""
    name: str | None = Field(None, min_length=1, max_length=255)
    owner_team: str | None = Field(None, max_length=255)
    owner_email: str | None = Field(None, max_length=255)


class ConnectGitHubRequest(BaseModel):
    """Request to store an encrypted GitHub access token on a repo."""
    access_token_encrypted: str = Field(..., min_length=1)


class CodeRepositoryResponse(BaseModel):
    """Code repository response."""
    id: str
    tenant_id: str
    name: str
    url: str
    owner_team: str | None
    owner_email: str | None
    scan_status: str
    last_scanned_at: str | None
    last_scan_commit_sha: str | None
    last_scan_error: str | None
    total_files_scanned: int
    total_endpoints_found: int
    created_at: str
    updated_at: str
    
    class Config:
        from_attributes = True


class EndpointUsageResponse(BaseModel):
    """Endpoint usage in a code repository."""
    endpoint_path: str
    http_method: str | None
    file_path: str
    line_number: int
    code_context: str | None
    confidence: float
    detection_method: str


class CodeRepositoryDetailResponse(CodeRepositoryResponse):
    """Code repository with endpoint usage details."""
    endpoint_usages: list[EndpointUsageResponse]


# Endpoints

@router.post("", response_model=CodeRepositoryResponse, status_code=201)
def create_code_repository(
    request: CreateCodeRepositoryRequest,
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_current_tenant_id),
):
    """
    Create a new code repository connection.
    
    This does not immediately scan - use POST /code-repositories/{id}/scan to trigger.
    """
    with tracer.start_as_current_span("api.create_code_repository"):
        try:
            # Extract installation_id if provided
            installation_id = getattr(request, 'installation_id', None)
            
            code_repository = CodeRepoRepository.create(
                db,
                tenant_id=tenant_id,
                name=request.name,
                url=request.url,
                owner_team=request.owner_team,
                owner_email=request.owner_email,
                github_installation_id=installation_id,
                access_token_encrypted=getattr(request, 'access_token_encrypted', None),
            )
            
            logger.info(f"Created code repository: {code_repository.id} for tenant {tenant_id}")
            
            return CodeRepositoryResponse(
                id=str(code_repository.id),
                tenant_id=code_repository.tenant_id,
                name=code_repository.name,
                url=code_repository.url,
                owner_team=code_repository.owner_team,
                owner_email=code_repository.owner_email,
                access_token_encrypted=code_repository.access_token_encrypted,
                scan_status=code_repository.scan_status,
                last_scanned_at=code_repository.last_scanned_at.isoformat() if code_repository.last_scanned_at else None,
                last_scan_commit_sha=code_repository.last_scan_commit_sha,
                last_scan_error=code_repository.last_scan_error,
                total_files_scanned=code_repository.total_files_scanned,
                total_endpoints_found=code_repository.total_endpoints_found,
                created_at=code_repository.created_at.isoformat(),
                updated_at=code_repository.updated_at.isoformat(),
            )
            
        except Exception as e:
            logger.exception(f"Failed to create code repository for tenant {tenant_id}")
            raise HTTPException(status_code=500, detail=str(e))

@router.get("", response_model=list[CodeRepositoryResponse])
def list_code_repositories(
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_current_tenant_id),
):
    """
    List all code repositories for the current tenant.
    """
    with tracer.start_as_current_span("api.list_code_repositories"):
        code_repositories = CodeRepoRepository.get_by_tenant(db, tenant_id)
        
        return [
            CodeRepositoryResponse(
                id=str(repo.id),
                tenant_id=repo.tenant_id,
                name=repo.name,
                url=repo.url,
                owner_team=repo.owner_team,
                owner_email=repo.owner_email,
                scan_status=repo.scan_status,
                last_scanned_at=repo.last_scanned_at.isoformat() if repo.last_scanned_at else None,
                last_scan_commit_sha=repo.last_scan_commit_sha,
                last_scan_error=repo.last_scan_error,
                total_files_scanned=repo.total_files_scanned,
                total_endpoints_found=repo.total_endpoints_found,
                created_at=repo.created_at.isoformat(),
                updated_at=repo.updated_at.isoformat(),
            )
            for repo in code_repositories
        ]


@router.get("/{code_repository_id}", response_model=CodeRepositoryDetailResponse)
def get_code_repository(
    code_repository_id: UUID,
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_current_tenant_id),
):
    """
    Get code repository details including endpoint usage.
    """
    with tracer.start_as_current_span("api.get_code_repository"):
        code_repository = CodeRepoRepository.get_by_id(db, code_repository_id)
        
        if not code_repository:
            raise HTTPException(status_code=404, detail="Code repository not found")
        
        if code_repository.tenant_id != tenant_id:
            raise HTTPException(status_code=403, detail="Access denied")
        
        return CodeRepositoryDetailResponse(
            id=str(code_repository.id),
            tenant_id=code_repository.tenant_id,
            name=code_repository.name,
            url=code_repository.url,
            owner_team=code_repository.owner_team,
            owner_email=code_repository.owner_email,
            scan_status=code_repository.scan_status,
            last_scanned_at=code_repository.last_scanned_at.isoformat() if code_repository.last_scanned_at else None,
            last_scan_commit_sha=code_repository.last_scan_commit_sha,
            last_scan_error=code_repository.last_scan_error,
            total_files_scanned=code_repository.total_files_scanned,
            total_endpoints_found=code_repository.total_endpoints_found,
            created_at=code_repository.created_at.isoformat(),
            updated_at=code_repository.updated_at.isoformat(),
            endpoint_usages=[
                EndpointUsageResponse(
                    endpoint_path=usage.endpoint_path,
                    http_method=usage.http_method,
                    file_path=usage.file_path,
                    line_number=usage.line_number,
                    code_context=usage.code_context,
                    confidence=usage.confidence,
                    detection_method=usage.detection_method,
                )
                for usage in code_repository.endpoint_usages
            ]
        )


@router.put("/{code_repository_id}", response_model=CodeRepositoryResponse)
def update_code_repository(
    code_repository_id: UUID,
    request: UpdateCodeRepositoryRequest,
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_current_tenant_id),
):
    """
    Update code repository details.
    """
    with tracer.start_as_current_span("api.update_code_repository"):
        code_repository = CodeRepoRepository.get_by_id(db, code_repository_id)
        
        if not code_repository:
            raise HTTPException(status_code=404, detail="Code repository not found")
        
        if code_repository.tenant_id != tenant_id:
            raise HTTPException(status_code=403, detail="Access denied")
        
        # Build update dict (only non-None values)
        updates = {}
        if request.name is not None:
            updates['name'] = request.name
        if request.owner_team is not None:
            updates['owner_team'] = request.owner_team
        if request.owner_email is not None:
            updates['owner_email'] = request.owner_email
        
        code_repository = CodeRepoRepository.update(db, code_repository, **updates)
        
        logger.info(f"Updated code repository: {code_repository_id}")
        
        return CodeRepositoryResponse(
            id=str(code_repository.id),
            tenant_id=code_repository.tenant_id,
            name=code_repository.name,
            url=code_repository.url,
            owner_team=code_repository.owner_team,
            owner_email=code_repository.owner_email,
            scan_status=code_repository.scan_status,
            last_scanned_at=code_repository.last_scanned_at.isoformat() if code_repository.last_scanned_at else None,
            last_scan_commit_sha=code_repository.last_scan_commit_sha,
            last_scan_error=code_repository.last_scan_error,
            total_files_scanned=code_repository.total_files_scanned,
            total_endpoints_found=code_repository.total_endpoints_found,
            created_at=code_repository.created_at.isoformat(),
            updated_at=code_repository.updated_at.isoformat(),
        )


@router.delete("/{code_repository_id}", status_code=204)
def delete_code_repository(
    code_repository_id: UUID,
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_current_tenant_id),
):
    """
    Delete a code repository.
    
    This will cascade delete all endpoint usage records.
    """
    with tracer.start_as_current_span("api.delete_code_repository"):
        code_repository = CodeRepoRepository.get_by_id(db, code_repository_id)
        
        if not code_repository:
            raise HTTPException(status_code=404, detail="Code repository not found")
        
        if code_repository.tenant_id != tenant_id:
            raise HTTPException(status_code=403, detail="Access denied")
        
        CodeRepoRepository.delete(db, code_repository)
        
        logger.info(f"Deleted code repository: {code_repository_id}")


@router.post("/{code_repository_id}/connect-github", response_model=CodeRepositoryResponse)
def connect_github(
    code_repository_id: UUID,
    request: ConnectGitHubRequest,
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_current_tenant_id),
):
    """
    Store an encrypted GitHub access token on a code repository.
    """
    with tracer.start_as_current_span("api.connect_github"):
        code_repository = CodeRepoRepository.get_by_id(db, code_repository_id)
        
        if not code_repository:
            raise HTTPException(status_code=404, detail="Code repository not found")
        
        if code_repository.tenant_id != tenant_id:
            raise HTTPException(status_code=403, detail="Access denied")
        
        code_repository = CodeRepoRepository.update(
            db,
            code_repository,
            access_token_encrypted=request.access_token_encrypted,
        )
        
        logger.info(f"Stored GitHub token for code repository: {code_repository_id}")
        
        return CodeRepositoryResponse(
            id=str(code_repository.id),
            tenant_id=code_repository.tenant_id,
            name=code_repository.name,
            url=code_repository.url,
            owner_team=code_repository.owner_team,
            owner_email=code_repository.owner_email,
            scan_status=code_repository.scan_status,
            last_scanned_at=code_repository.last_scanned_at.isoformat() if code_repository.last_scanned_at else None,
            last_scan_commit_sha=code_repository.last_scan_commit_sha,
            last_scan_error=code_repository.last_scan_error,
            total_files_scanned=code_repository.total_files_scanned,
            total_endpoints_found=code_repository.total_endpoints_found,
            created_at=code_repository.created_at.isoformat(),
            updated_at=code_repository.updated_at.isoformat(),
        )


@router.post("/{code_repository_id}/scan", status_code=202)
async def trigger_scan(
    code_repository_id: UUID,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_current_tenant_id),
):
    """
    Trigger a scan of the code repository.
    
    Clones from GitHub and scans for API endpoint usage.
    """
    with tracer.start_as_current_span("api.trigger_scan"):
        code_repository = CodeRepoRepository.get_by_id(db, code_repository_id)
        
        if not code_repository:
            raise HTTPException(status_code=404, detail="Code repository not found")
        
        if code_repository.tenant_id != tenant_id:
            raise HTTPException(status_code=403, detail="Access denied")
        
        # Check if we have installation ID
        if not code_repository.github_installation_id:
            raise HTTPException(
                status_code=400,
                detail="No GitHub App installation. Please connect via GitHub App first."
            )
        
        # Get installation token
        from avanamy.services.github_app_service import GitHubAppService
        from avanamy.services.code_repo_scanner_service import CodeRepoScannerService
        
        app_service = GitHubAppService()
        
        # Trigger scan in background
        async def scan_task():
            scanner_service = CodeRepoScannerService(db)
            try:
                # Get fresh installation token
                installation_token = await app_service.get_installation_token(
                    code_repository.github_installation_id
                )
                
                await scanner_service.scan_repository_from_github(
                    code_repository_id=code_repository_id,
                    access_token=installation_token
                )
            except Exception as e:
                logger.exception(f"Background scan failed: {e}")
        
        background_tasks.add_task(scan_task)
        
        # Update status immediately
        CodeRepoRepository.update(db, code_repository, scan_status="pending")
        
        logger.info(f"Scan triggered for code repository: {code_repository_id}")
        
        return {
            "message": "Scan triggered",
            "code_repository_id": str(code_repository_id),
            "status": "pending"
        }
