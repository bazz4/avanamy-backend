# src/avanamy/api/routes/github_app.py

"""
GitHub App installation endpoints.
"""

import logging
import secrets
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel
from opentelemetry import trace
from datetime import datetime, timezone

from avanamy.db.database import get_db
from avanamy.auth.clerk import get_current_tenant_id
from avanamy.services.github_app_service import GitHubAppService
from avanamy.services.encryption_service import get_encryption_service

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)
router = APIRouter(prefix="/github", tags=["github-app"])


# In-memory state store (use Redis in production)
_oauth_states = {}


class GitHubAuthResponse(BaseModel):
    """GitHub authorization response."""
    authorization_url: str
    state: str


class GitHubCallbackRequest(BaseModel):
    """GitHub OAuth callback data."""
    code: str
    state: str


class GitHubTokenResponse(BaseModel):
    """GitHub access token response."""
    access_token_encrypted: str
    installation_id: int
    user_info: dict


@router.get("/authorize", response_model=GitHubAuthResponse)
def authorize(
    tenant_id: str = Depends(get_current_tenant_id),
):
    """
    Initiate GitHub App installation flow.
    
    Returns installation URL for user to visit.
    """
    with tracer.start_as_current_span("api.github_authorize"):
        try:
            app_service = GitHubAppService()
            
            # Generate CSRF state token
            state = secrets.token_urlsafe(32)
            
            # Store state with tenant (expires after 10 minutes)
            _oauth_states[state] = {
                "tenant_id": tenant_id,
                "created_at": datetime.now(timezone.utc)
            }
            
            # Generate installation URL
            install_url = app_service.get_installation_url(state)
            
            logger.info(f"Generated GitHub App installation URL for tenant: {tenant_id}")
            
            return GitHubAuthResponse(
                authorization_url=install_url,
                state=state
            )
            
        except Exception as e:
            logger.exception("Failed to generate GitHub App installation URL")
            raise HTTPException(status_code=500, detail=str(e))


@router.post("/callback", response_model=GitHubTokenResponse)
async def callback(
    request: GitHubCallbackRequest,
    db: Session = Depends(get_db),
):
    """
    Handle GitHub App installation callback.
    
    Exchanges code for access token and installation ID.
    """
    with tracer.start_as_current_span("api.github_callback"):
        try:
            # Verify state
            if request.state not in _oauth_states:
                raise HTTPException(status_code=400, detail="Invalid state parameter")
            
            state_data = _oauth_states.pop(request.state)
            tenant_id = state_data["tenant_id"]
            
            # Exchange code for token and installation ID
            app_service = GitHubAppService()
            result = await app_service.exchange_code_for_token(request.code)
            
            access_token = result["access_token"]
            installation_id = result["installation_id"]
            
            # Get user info
            user_info = await app_service.get_user_info(access_token)
            
            # Encrypt access token
            encryption_service = get_encryption_service()
            encrypted_token = encryption_service.encrypt(access_token)
            
            logger.info(
                f"GitHub App installation successful: "
                f"tenant={tenant_id}, user={user_info.get('login')}, installation_id={installation_id}"
            )
            
            return GitHubTokenResponse(
                access_token_encrypted=encrypted_token,
                installation_id=installation_id,
                user_info=user_info
            )
            
        except Exception as e:
            logger.exception("GitHub App callback failed")
            raise HTTPException(status_code=500, detail=str(e))


@router.get("/repositories")
async def list_repositories(
    installation_id: int = Query(...),
    tenant_id: str = Depends(get_current_tenant_id),
):
    """
    List GitHub repositories accessible via installation.
    
    This helps users select which repo to scan.
    """
    with tracer.start_as_current_span("api.github_list_repositories"):
        try:
            from avanamy.services.github_app_service import GitHubAppService
            
            # Get installation token using App JWT
            app_service = GitHubAppService()
            installation_token = await app_service.get_installation_token(installation_id)
            
            # Use installation token to list repos via GitHub API
            url = "https://api.github.com/installation/repositories"
            
            headers = {
                "Authorization": f"Bearer {installation_token}",
                "Accept": "application/vnd.github.v3+json"
            }
            
            import httpx
            async with httpx.AsyncClient() as client:
                response = await client.get(url, headers=headers)
                response.raise_for_status()
                
                data = response.json()
                repos = data.get("repositories", [])
                
                result = []
                for repo in repos:
                    result.append({
                        "name": repo["name"],
                        "full_name": repo["full_name"],
                        "clone_url": repo["clone_url"],
                        "default_branch": repo.get("default_branch", "main"),
                        "private": repo["private"],
                    })
                
                logger.info(f"Listed {len(result)} repositories for installation: {installation_id}")
                
                return {
                    "repositories": result
                }
            
        except Exception as e:
            logger.exception("Failed to list GitHub repositories")
            raise HTTPException(status_code=500, detail=str(e))