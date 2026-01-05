# src/avanamy/api/routes/github_oauth.py

"""
GitHub OAuth endpoints.
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
from avanamy.services.github_oauth_service import GitHubOAuthService
from avanamy.services.encryption_service import get_encryption_service

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)
router = APIRouter(prefix="/github", tags=["github-oauth"])


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
    user_info: dict


@router.get("/authorize", response_model=GitHubAuthResponse)
def authorize(
    tenant_id: str = Depends(get_current_tenant_id),
):
    """
    Initiate GitHub OAuth flow.
    
    Returns authorization URL for user to visit.
    """
    with tracer.start_as_current_span("api.github_authorize"):
        try:
            oauth_service = GitHubOAuthService()
            
            # Generate CSRF state token
            state = secrets.token_urlsafe(32)
            
            # Store state with tenant (expires after 10 minutes)
            _oauth_states[state] = {
                "tenant_id": tenant_id,
                "created_at": datetime.now(timezone.utc)
            }
            
            # Generate authorization URL
            auth_url = oauth_service.get_authorization_url(state)
            
            logger.info(f"Generated GitHub auth URL for tenant: {tenant_id}")
            
            return GitHubAuthResponse(
                authorization_url=auth_url,
                state=state
            )
            
        except Exception as e:
            logger.exception("Failed to generate GitHub auth URL")
            raise HTTPException(status_code=500, detail=str(e))


@router.post("/callback", response_model=GitHubTokenResponse)
async def callback(
    request: GitHubCallbackRequest,
    db: Session = Depends(get_db),
):
    """
    Handle GitHub OAuth callback.
    
    Exchanges code for access token and encrypts it.
    """
    with tracer.start_as_current_span("api.github_callback"):
        try:
            # Verify state
            if request.state not in _oauth_states:
                raise HTTPException(status_code=400, detail="Invalid state parameter")
            
            state_data = _oauth_states.pop(request.state)
            tenant_id = state_data["tenant_id"]
            
            # Exchange code for token
            oauth_service = GitHubOAuthService()
            access_token = await oauth_service.exchange_code_for_token(request.code)
            
            # Get user info
            user_info = await oauth_service.get_user_info(access_token)
            
            # Encrypt access token
            encryption_service = get_encryption_service()
            encrypted_token = encryption_service.encrypt(access_token)
            
            logger.info(f"GitHub OAuth successful for tenant: {tenant_id}, user: {user_info.get('login')}")
            
            return GitHubTokenResponse(
                access_token_encrypted=encrypted_token,
                user_info=user_info
            )
            
        except Exception as e:
            logger.exception("GitHub OAuth callback failed")
            raise HTTPException(status_code=500, detail=str(e))


@router.get("/repositories")
async def list_repositories(
    access_token_encrypted: str = Query(...),
    tenant_id: str = Depends(get_current_tenant_id),
):
    """
    List GitHub repositories accessible with provided token.
    
    This helps users select which repo to scan.
    """
    with tracer.start_as_current_span("api.github_list_repositories"):
        try:
            from avanamy.services.github_api_service import GitHubAPIService
            
            # Decrypt token
            encryption_service = get_encryption_service()
            access_token = encryption_service.decrypt(access_token_encrypted)
            
            # List repositories
            github_service = GitHubAPIService(access_token)
            repositories = await github_service.list_repositories()
            
            logger.info(f"Listed {len(repositories)} repositories for tenant: {tenant_id}")
            
            return {
                "repositories": repositories
            }
            
        except Exception as e:
            logger.exception("Failed to list GitHub repositories")
            raise HTTPException(status_code=500, detail=str(e))