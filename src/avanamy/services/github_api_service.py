# src/avanamy/services/github_api_service.py

"""
GitHub API service for repository operations.
"""

import os
import tempfile
import shutil
import logging
from typing import List, Tuple
from github import Github, GithubException
from git import Repo
from opentelemetry import trace

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


class GitHubAPIService:
    """
    Service for interacting with GitHub repositories.
    """
    
    def __init__(self, access_token: str):
        """
        Initialize with GitHub access token.
        
        Args:
            access_token: GitHub personal access token
        """
        self.github = Github(access_token)
        self.access_token = access_token
    
    async def list_repositories(self, installation_id: int) -> List[dict]:
        """
        List repositories accessible via GitHub App installation.
        
        Args:
            installation_id: GitHub installation ID
            
        Returns:
            List of repository dicts
        """
        with tracer.start_as_current_span("github.list_repositories"):
            try:
                from avanamy.services.github_app_service import GitHubAppService
                
                # Get installation token
                app_service = GitHubAppService()
                installation_token = await app_service.get_installation_token(installation_id)
                
                # Use installation token to list repos
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
                    
                    logger.info(f"Listed {len(result)} installation repositories")
                    return result
                    
            except Exception as e:
                logger.exception("Failed to list repositories")
                raise ValueError(f"Failed to list repositories: {e}")
    
    def clone_repository(self, repo_url: str, target_dir: str) -> Tuple[str, str]:
        """
        Clone a GitHub repository.
        
        Args:
            repo_url: Repository clone URL
            target_dir: Directory to clone into
            
        Returns:
            Tuple of (repo_path, commit_sha)
        """
        with tracer.start_as_current_span("github.clone_repository") as span:
            span.set_attribute("repo_url", repo_url)
            
            try:
                # Add authentication to clone URL
                # Format: https://x-access-token:<token>@github.com/user/repo.git
                if repo_url.startswith("https://github.com/"):
                    auth_url = repo_url.replace(
                        "https://github.com/",
                        f"https://x-access-token:{self.access_token}@github.com/"
                    )
                else:
                    auth_url = repo_url
                
                logger.info(f"Cloning repository to {target_dir}")
                
                # Clone the repository
                repo = Repo.clone_from(auth_url, target_dir, depth=1)
                
                # Get current commit SHA
                commit_sha = repo.head.commit.hexsha
                
                logger.info(f"Successfully cloned repository, commit: {commit_sha}")
                span.set_attribute("commit_sha", commit_sha)
                
                return target_dir, commit_sha
                
            except Exception as e:
                logger.exception("Failed to clone repository")
                span.set_attribute("error", str(e))
                raise ValueError(f"Failed to clone repository: {e}")
    
    def verify_access(self, repo_full_name: str) -> bool:
        """
        Verify that we have access to a repository.
        
        Args:
            repo_full_name: Repository full name (e.g., "owner/repo")
            
        Returns:
            True if we have access
        """
        with tracer.start_as_current_span("github.verify_access"):
            try:
                repo = self.github.get_repo(repo_full_name)
                # Try to get repo info to verify access
                _ = repo.name
                logger.info(f"Verified access to {repo_full_name}")
                return True
                
            except GithubException as e:
                logger.warning(f"No access to {repo_full_name}: {e}")
                return False
            

print("github_api_service loaded, globals:", list(globals().keys()))
