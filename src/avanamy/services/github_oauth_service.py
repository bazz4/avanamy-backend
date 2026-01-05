# src/avanamy/services/github_oauth_service.py

"""
GitHub OAuth service for user authentication and token management.
"""

import os
import logging
import httpx
from opentelemetry import trace

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


class GitHubOAuthService:
    """
    Service for GitHub OAuth flow.
    """
    
    def __init__(self):
        """Initialize with GitHub OAuth credentials."""
        self.client_id = os.getenv("GITHUB_CLIENT_ID")
        self.client_secret = os.getenv("GITHUB_CLIENT_SECRET")
        
        if not self.client_id or not self.client_secret:
            raise ValueError("GitHub OAuth credentials not configured")
    
    def get_authorization_url(self, state: str) -> str:
        """
        Generate GitHub OAuth authorization URL.
        
        Args:
            state: CSRF protection token
            
        Returns:
            Authorization URL to redirect user to
        """
        scopes = "repo"  # Request read access to repositories
        
        url = (
            f"https://github.com/login/oauth/authorize"
            f"?client_id={self.client_id}"
            f"&scope={scopes}"
            f"&state={state}"
        )
        
        logger.info("Generated GitHub authorization URL")
        return url
    
    async def exchange_code_for_token(self, code: str) -> str:
        """
        Exchange authorization code for access token.
        
        Args:
            code: Authorization code from GitHub callback
            
        Returns:
            Access token
        """
        with tracer.start_as_current_span("github.exchange_code") as span:
            span.set_attribute("code_length", len(code))
            
            url = "https://github.com/login/oauth/access_token"
            
            data = {
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "code": code,
            }
            
            headers = {
                "Accept": "application/json"
            }
            
            async with httpx.AsyncClient() as client:
                try:
                    response = await client.post(url, data=data, headers=headers)
                    response.raise_for_status()
                    
                    result = response.json()
                    
                    if "access_token" not in result:
                        error = result.get("error_description", "Unknown error")
                        logger.error(f"GitHub token exchange failed: {error}")
                        raise ValueError(f"Token exchange failed: {error}")
                    
                    access_token = result["access_token"]
                    
                    logger.info("Successfully exchanged code for access token")
                    span.set_attribute("success", True)
                    
                    return access_token
                    
                except httpx.HTTPError as e:
                    logger.exception("HTTP error during token exchange")
                    span.set_attribute("error", str(e))
                    raise ValueError(f"Failed to exchange code for token: {e}")
    
    async def get_user_info(self, access_token: str) -> dict:
        """
        Get GitHub user information.
        
        Args:
            access_token: GitHub access token
            
        Returns:
            User info dict with keys: login, id, name, email
        """
        with tracer.start_as_current_span("github.get_user_info"):
            url = "https://api.github.com/user"
            
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/vnd.github.v3+json"
            }
            
            async with httpx.AsyncClient() as client:
                try:
                    response = await client.get(url, headers=headers)
                    response.raise_for_status()
                    
                    user_data = response.json()
                    
                    logger.info(f"Retrieved user info for: {user_data.get('login')}")
                    
                    return {
                        "login": user_data.get("login"),
                        "id": user_data.get("id"),
                        "name": user_data.get("name"),
                        "email": user_data.get("email"),
                    }
                    
                except httpx.HTTPError as e:
                    logger.exception("Failed to get user info")
                    raise ValueError(f"Failed to get user info: {e}")