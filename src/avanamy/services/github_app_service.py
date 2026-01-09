# src/avanamy/services/github_app_service.py

"""
GitHub App service for installation-based authentication.
"""

import os
import time
import logging
import httpx
import jwt
from opentelemetry import trace

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


class GitHubAppService:
    """
    Service for GitHub App installation flow.
    Uses installation tokens (not user OAuth tokens).
    """
    
    def __init__(self):
        """Initialize with GitHub App credentials."""
        self.app_id = os.getenv("GITHUB_APP_ID")
        self.client_id = os.getenv("GITHUB_CLIENT_ID")
        self.client_secret = os.getenv("GITHUB_CLIENT_SECRET")
        self.private_key_path = os.getenv("GITHUB_PRIVATE_KEY_PATH")
        
        if not all([self.app_id, self.client_id, self.client_secret, self.private_key_path]):
            raise ValueError("GitHub App credentials not fully configured")
        
        # Load private key
        with open(self.private_key_path, 'r') as f:
            self.private_key = f.read()
    
    def generate_jwt(self) -> str:
        """
        Generate JWT for GitHub App authentication.
        
        Returns:
            JWT token
        """
        now = int(time.time())
        payload = {
            'iat': now,
            'exp': now + (10 * 60),  # Expires in 10 minutes
            'iss': self.app_id
        }
        
        token = jwt.encode(payload, self.private_key, algorithm='RS256')
        return token
    
    def get_installation_url(self, state: str) -> str:
        """
        Generate GitHub App installation URL.
        
        Args:
            state: CSRF protection token
            
        Returns:
            Installation URL to redirect user to
        """
        # Use setup URL which works for both new and existing installations
        url = (
            f"https://github.com/login/oauth/authorize"
            f"?client_id={self.client_id}"
            f"&redirect_uri={os.getenv('FRONTEND_URL')}/auth/github/callback"
            f"&state={state}"
        )
        
        logger.info("Generated GitHub App installation URL")
        return url
        
    async def exchange_code_for_token(self, code: str) -> dict:
        """
        Exchange authorization code for installation access token.
        
        Args:
            code: Authorization code from GitHub callback
            
        Returns:
            Dict with access_token and installation_id
        """
        with tracer.start_as_current_span("github.exchange_code") as span:
            url = "https://github.com/login/oauth/access_token"
            
            data = {
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "code": code,
            }
            
            headers = {"Accept": "application/json"}
            
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
                    
                    # Get installation ID for this token
                    installation_id = await self._get_installation_id(access_token)
                    
                    logger.info(f"Successfully exchanged code, installation_id: {installation_id}")
                    span.set_attribute("success", True)
                    span.set_attribute("installation_id", installation_id)
                    
                    return {
                        "access_token": access_token,
                        "installation_id": installation_id
                    }
                    
                except httpx.HTTPError as e:
                    logger.exception("HTTP error during token exchange")
                    span.set_attribute("error", str(e))
                    raise ValueError(f"Failed to exchange code for token: {e}")
    
    async def _get_installation_id(self, user_token: str) -> int:
        """
        Get installation ID from user token.
        
        Args:
            user_token: User access token
            
        Returns:
            Installation ID
        """
        url = "https://api.github.com/user/installations"
        
        headers = {
            "Authorization": f"Bearer {user_token}",
            "Accept": "application/vnd.github.v3+json"
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            
            data = response.json()
            installations = data.get("installations", [])
            
            if not installations:
                raise ValueError("No GitHub App installations found")
            
            # Return first installation (most users have one)
            return installations[0]["id"]
    
    async def get_installation_token(self, installation_id: int) -> str:
        """
        Get installation access token using JWT.
        
        Args:
            installation_id: GitHub installation ID
            
        Returns:
            Installation access token
        """
        with tracer.start_as_current_span("github.get_installation_token"):
            jwt_token = self.generate_jwt()
            
            url = f"https://api.github.com/app/installations/{installation_id}/access_tokens"
            
            headers = {
                "Authorization": f"Bearer {jwt_token}",
                "Accept": "application/vnd.github.v3+json"
            }
            
            async with httpx.AsyncClient() as client:
                try:
                    response = await client.post(url, headers=headers)
                    response.raise_for_status()
                    
                    data = response.json()
                    token = data["token"]
                    
                    logger.info(f"Got installation token for installation_id: {installation_id}")
                    
                    return token
                    
                except httpx.HTTPError as e:
                    logger.exception(f"Failed to get installation token")
                    raise ValueError(f"Failed to get installation token: {e}")
    
    async def get_user_info(self, access_token: str) -> dict:
        """
        Get GitHub user information.
        
        Args:
            access_token: GitHub access token
            
        Returns:
            User info dict
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