"""
Polling service for monitoring external API specs.

This service fetches specs from external URLs, detects changes,
and creates new versions automatically.
"""

import hashlib
import httpx
import logging
from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session
from opentelemetry import trace

from avanamy.models.watched_api import WatchedAPI
from avanamy.services.api_spec_service import update_api_spec_file
from avanamy.services.api_spec_parser import parse_api_spec

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


class PollingService:
    """Service for polling external APIs and detecting spec changes."""

    def __init__(self, db: Session):
        self.db = db

    async def poll_watched_api(self, watched_api_id: UUID) -> dict:
        """
        Poll a single watched API for changes.
        
        Returns a dict with status and details:
        {
            "status": "success" | "no_change" | "error",
            "version_created": int | None,
            "error": str | None
        }
        """
        with tracer.start_as_current_span("poll_watched_api") as span:
            span.set_attribute("watched_api_id", str(watched_api_id))
            
            # Load the watched API
            watched_api = self.db.query(WatchedAPI).filter(
                WatchedAPI.id == watched_api_id
            ).first()
            
            if not watched_api:
                logger.error(f"WatchedAPI {watched_api_id} not found")
                return {"status": "error", "error": "WatchedAPI not found"}
            
            if not watched_api.polling_enabled:
                logger.info(f"Polling disabled for {watched_api.spec_url}")
                return {"status": "skipped", "error": "Polling disabled"}
            
            try:
                # Fetch the spec from external URL
                spec_content = await self._fetch_spec(watched_api.spec_url)
                
                # Compute hash to detect changes
                spec_hash = self._hash_spec(spec_content)
                span.set_attribute("spec_hash", spec_hash)
                
                # Check if spec has changed
                if spec_hash == watched_api.last_spec_hash:
                    logger.info(f"No changes detected for {watched_api.spec_url}")
                    self._update_poll_tracking(watched_api, success=True, error=None)
                    return {"status": "no_change"}
                
                # Spec has changed! Create new version
                logger.info(f"Changes detected for {watched_api.spec_url}, creating new version")
                
                # Parse the spec to determine format
                try:
                    parsed_spec = parse_api_spec("spec.yaml", spec_content)
                    spec_format = parsed_spec.get("openapi", parsed_spec.get("swagger", "unknown"))
                except Exception as parse_error:
                    logger.warning(f"Could not parse spec format: {parse_error}")
                    spec_format = "unknown"
                
                # Create new version using existing service
                # This will:
                # 1. Store spec in S3
                # 2. Generate normalized spec
                # 3. Compute diff (if not v1)
                # 4. Generate AI summary
                new_version = await self._create_new_version(
                    watched_api=watched_api,
                    spec_content=spec_content,
                    spec_hash=spec_hash
                )
                
                # Update tracking
                watched_api.last_spec_hash = spec_hash
                watched_api.last_version_detected = new_version
                self._update_poll_tracking(watched_api, success=True, error=None)
                
                logger.info(
                    f"Successfully created version {new_version} for {watched_api.spec_url}"
                )
                span.set_attribute("version_created", new_version)
                
                return {
                    "status": "success",
                    "version_created": new_version
                }
                
            except httpx.HTTPStatusError as e:
                error_msg = f"HTTP {e.response.status_code}: {e.response.text[:200]}"
                logger.error(f"Failed to fetch {watched_api.spec_url}: {error_msg}")
                self._update_poll_tracking(watched_api, success=False, error=error_msg)
                return {"status": "error", "error": error_msg}
            
            except Exception as e:
                error_msg = str(e)
                logger.exception(f"Error polling {watched_api.spec_url}")
                self._update_poll_tracking(watched_api, success=False, error=error_msg)
                return {"status": "error", "error": error_msg}

    async def _fetch_spec(self, url: str) -> str:
        """
        Fetch API spec from external URL.
        
        For MVP: No authentication, just public URLs.
        """
        logger.info(f"Fetching spec from {url}")
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url)
            response.raise_for_status()
            
            content = response.text
            logger.info(f"Fetched {len(content)} bytes from {url}")
            
            return content

    def _hash_spec(self, spec_content: str) -> str:
        """Compute SHA256 hash of spec content for change detection."""
        return hashlib.sha256(spec_content.encode()).hexdigest()

    async def _create_new_version(
        self,
        watched_api: WatchedAPI,
        spec_content: str,
        spec_hash: str
    ) -> int:
        """
        Create a new version entry for the changed spec.
        
        This reuses the existing update_api_spec_file service which handles:
        - Storing spec in S3
        - Generating normalized spec
        - Computing diff
        - Generating AI summary
        """
        from avanamy.models.api_spec import ApiSpec
        from avanamy.models.version_history import VersionHistory
        
        # Get or create the ApiSpec for this API product
        api_spec = self.db.query(ApiSpec).filter(
            ApiSpec.api_product_id == watched_api.api_product_id
        ).first()
        
        if not api_spec:
            # Create new ApiSpec if it doesn't exist
            api_spec = ApiSpec(
                api_product_id=watched_api.api_product_id,
                name=f"API Spec from {watched_api.spec_url}"
            )
            self.db.add(api_spec)
            self.db.flush()  # Get the ID
        
        # Determine filename based on URL
        filename = self._extract_filename(watched_api.spec_url)
        
        # Call existing service to handle the upload
        updated_spec = update_api_spec_file(
            db=self.db,
            spec=api_spec,
            file_bytes=spec_content.encode(),
            filename=filename,
            tenant_id=str(watched_api.tenant_id),
            description=f"Auto-detected change from {watched_api.spec_url}"
        )
        
        # Get the latest version number
        latest_version = self.db.query(VersionHistory).filter(
            VersionHistory.api_spec_id == updated_spec.id
        ).order_by(VersionHistory.version.desc()).first()
        
        if latest_version:
            return latest_version.version
        else:
            return 1

    def _extract_filename(self, url: str) -> str:
        """Extract a reasonable filename from the URL."""
        # Get last part of URL
        parts = url.rstrip('/').split('/')
        filename = parts[-1] if parts else "spec.yaml"
        
        # Ensure it has an extension
        if '.' not in filename:
            filename = filename + ".yaml"
        
        return filename

    def _update_poll_tracking(
        self,
        watched_api: WatchedAPI,
        success: bool,
        error: Optional[str]
    ):
        """Update polling tracking fields on the WatchedAPI."""
        watched_api.last_polled_at = datetime.now()
        
        if success:
            watched_api.last_successful_poll_at = datetime.now()
            watched_api.consecutive_failures = 0
            watched_api.last_error = None
            watched_api.status = "active"
        else:
            watched_api.consecutive_failures += 1
            watched_api.last_error = error
            
            # After 5 consecutive failures, mark as failed
            if watched_api.consecutive_failures >= 5:
                watched_api.status = "failed"
                logger.warning(
                    f"WatchedAPI {watched_api.id} marked as failed after "
                    f"{watched_api.consecutive_failures} consecutive failures"
                )
        
        self.db.commit()


async def poll_all_active_apis(db: Session) -> dict:
    """
    Poll all active watched APIs.
    
    Returns summary of results:
    {
        "total": 10,
        "success": 8,
        "no_change": 5,
        "errors": 2,
        "versions_created": [1, 2, 3]
    }
    """
    logger.info("Starting poll of all active watched APIs")
    
    # Get all active watched APIs
    watched_apis = db.query(WatchedAPI).filter(
        WatchedAPI.status == "active",
        WatchedAPI.polling_enabled == True
    ).all()
    
    results = {
        "total": len(watched_apis),
        "success": 0,
        "no_change": 0,
        "errors": 0,
        "versions_created": []
    }
    
    service = PollingService(db)
    
    for watched_api in watched_apis:
        result = await service.poll_watched_api(watched_api.id)
        
        if result["status"] == "success":
            results["success"] += 1
            if result.get("version_created"):
                results["versions_created"].append(result["version_created"])
        elif result["status"] == "no_change":
            results["no_change"] += 1
        elif result["status"] == "error":
            results["errors"] += 1
    
    logger.info(f"Polling complete: {results}")
    return results