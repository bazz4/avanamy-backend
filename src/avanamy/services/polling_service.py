"""
Polling service for monitoring external API specs.

This service fetches specs from external URLs, detects changes,
and creates new versions automatically.
"""

import hashlib
import httpx
import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session
from opentelemetry import trace

from avanamy.models.watched_api import WatchedAPI
from avanamy.models.version_history import VersionHistory
from avanamy.services.api_spec_service import update_api_spec_file
from avanamy.services.alert_service import AlertService
from avanamy.services.endpoint_health_service import EndpointHealthService
from avanamy.services.api_spec_parser import parse_api_spec
from avanamy.services.email_service import EmailService
from avanamy.models.alert_configuration import AlertConfiguration

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


class PollingService:
    """Service for polling external APIs and detecting spec changes."""

    def __init__(self, db: Session):
        self.db = db
        self.email_service = EmailService()
        
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
                
                # Run endpoint health checks (independent of spec changes)
                health_results = await self._run_health_checks(watched_api, spec_content)
                
                # Check if spec has changed
                if spec_hash == watched_api.last_spec_hash:
                    logger.info(f"No changes detected for {watched_api.spec_url}")
                    self._update_poll_tracking(watched_api, success=True, error=None)
                    return {
                        "status": "no_change",
                        "health_checks": health_results
                    }
                
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
                
                # Check for breaking changes and send alerts
                await self._check_and_alert_breaking_changes(watched_api, new_version)
                
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
        # Determine filename based on URL
        filename = self._extract_filename(watched_api.spec_url)
        
        # Call existing service to handle the upload
        # Note: update_api_spec_file expects spec_id, not provider/product IDs
        api_spec = update_api_spec_file(
            db=self.db,
            spec_id=watched_api.api_spec_id,  # ← Use spec_id instead
            filename=filename,
            raw_content=spec_content.encode(),
            changelog=f"Auto-detected change from {watched_api.spec_url}"
        )
        
        # Get the latest version for this spec
        from avanamy.models.version_history import VersionHistory
        
        latest_version = self.db.query(VersionHistory).filter(
            VersionHistory.api_spec_id == api_spec.id
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
        watched_api.last_polled_at = datetime.now(timezone.utc)
        
        if success:
            watched_api.last_successful_poll_at = datetime.now(timezone.utc)
            watched_api.consecutive_failures = 0
            watched_api.last_error = None
            watched_api.status = "active"
        else:
            watched_api.consecutive_failures += 1
            watched_api.last_error = error
            
            # Send alert on 3rd consecutive failure
            if watched_api.consecutive_failures == 3:
                logger.warning(
                    f"WatchedAPI {watched_api.id} has failed 3 times, sending alerts"
                )
                
                # Get alert configurations
                alert_configs = (
                    self.db.query(AlertConfiguration)
                    .filter(
                        AlertConfiguration.watched_api_id == watched_api.id,
                        AlertConfiguration.enabled == True,
                        AlertConfiguration.alert_on_endpoint_failures == True
                    )
                    .all()
                )
                
                # Send alert for each configuration
                for config in alert_configs:
                    self.email_service.send_endpoint_down_alert(
                        db=self.db,
                        alert_config=config,
                        watched_api=watched_api,
                        endpoint_path=watched_api.spec_url,  # Use the spec URL as "endpoint"
                        http_method="GET",
                        status_code=401 if "401" in error else 500,
                        error_message=error
                    )
                
                logger.info(f"Sent {len(alert_configs)} poll failure alerts")
            
            # After 5 consecutive failures, mark as failed
            if watched_api.consecutive_failures >= 5:
                watched_api.status = "failed"
                logger.warning(
                    f"WatchedAPI {watched_api.id} marked as failed after "
                    f"{watched_api.consecutive_failures} consecutive failures"
                )
        
        self.db.commit()

    async def _check_and_alert_breaking_changes(
        self,
        watched_api: WatchedAPI,
        version_number: int
    ):
        """
        Check if the new version has breaking changes and send alerts.
        
        Args:
            watched_api: The WatchedAPI that was updated
            version_number: The version number that was just created
        """
        try:
            # Ensure api_spec_id is set
            if not watched_api.api_spec_id:
                logger.warning(f"WatchedAPI {watched_api.id} has no api_spec_id set")
                return
            
            # Get the version history record
            version_history = self.db.query(VersionHistory).filter(
                VersionHistory.api_spec_id == watched_api.api_spec_id,
                VersionHistory.version == version_number
            ).first()
            
            if not version_history:
                logger.warning(f"Version history not found for version {version_number}")
                return
            
            # Check if there's a diff and if it contains breaking changes
            if not version_history.diff:
                logger.info(f"No diff found for version {version_number}")
                return
            
            diff = version_history.diff
            
            # Check for breaking changes
            breaking_changes = diff.get('breaking_changes', [])
            is_breaking = len(breaking_changes) > 0
            
            if is_breaking:
                logger.info(
                    f"Breaking changes detected in version {version_number}, sending alerts"
                )
                
                # Get alert configurations
                alert_configs = (
                    self.db.query(AlertConfiguration)
                    .filter(
                        AlertConfiguration.watched_api_id == watched_api.id,
                        AlertConfiguration.enabled == True,
                        AlertConfiguration.alert_on_breaking_changes == True
                    )
                    .all()
                )
                
                # Send alert for each configuration
                for config in alert_configs:
                    self.email_service.send_breaking_change_alert(
                        db=self.db,
                        alert_config=config,
                        watched_api=watched_api,
                        version=version_history,
                        breaking_changes_count=len(breaking_changes)
                    )
                
                logger.info(f"Sent {len(alert_configs)} breaking change alerts")
            
            # Also check for non-breaking changes (optional)
            elif diff:
                # Get configs that want non-breaking alerts
                alert_configs = (
                    self.db.query(AlertConfiguration)
                    .filter(
                        AlertConfiguration.watched_api_id == watched_api.id,
                        AlertConfiguration.enabled == True,
                        AlertConfiguration.alert_on_non_breaking_changes == True
                    )
                    .all()
                )
                
                for config in alert_configs:
                    self.email_service.send_non_breaking_change_alert(
                        db=self.db,
                        alert_config=config,
                        watched_api=watched_api,
                        version=version_history
                    )
                
                logger.info(f"Sent {len(alert_configs)} non-breaking change alerts")
            
        except Exception as e:
            logger.error(f"Error checking/alerting breaking changes: {e}", exc_info=True)
            # Don't fail the polling if alerting fails

    async def _run_health_checks(
        self,
        watched_api: WatchedAPI,
        spec_content: str
    ) -> dict:
        """
        Run endpoint health checks for this API.
        
        Args:
            watched_api: The WatchedAPI to check
            spec_content: The OpenAPI spec content
        
        Returns:
            Dict with health check results
        """
        try:
            logger.info(f"Running health checks for {watched_api.spec_url}")
            
            health_service = EndpointHealthService(self.db)
            results = await health_service.check_endpoints(watched_api, spec_content)
            
            logger.info(
                f"Health checks complete: {results['healthy']} healthy, "
                f"{results['unhealthy']} unhealthy"
            )
            
            return results
            
        except Exception as e:
            logger.error(f"Error running health checks: {e}", exc_info=True)
            return {
                "total": 0,
                "healthy": 0,
                "unhealthy": 0,
                "error": str(e)
            }


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