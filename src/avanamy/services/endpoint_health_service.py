"""
Endpoint health monitoring service.

Checks the health of individual API endpoints by making actual HTTP requests
and tracking success/failure over time.
"""

import logging
import httpx
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy.orm import Session
from opentelemetry import trace
from prometheus_client import Gauge, Histogram, Counter

from avanamy.models.watched_api import WatchedAPI
from avanamy.models.endpoint_health import EndpointHealth
from avanamy.services.alert_service import AlertService

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)

# Prometheus metrics
endpoint_health_status = Gauge(
    'endpoint_health_status',
    'Current health status of monitored endpoints (1=healthy, 0=down)',
    ['watched_api_id', 'endpoint_path', 'http_method']
)

endpoint_response_time_seconds = Histogram(
    'endpoint_response_time_seconds',
    'Response time of monitored endpoints in seconds',
    ['watched_api_id', 'endpoint_path', 'http_method'],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0]
)

endpoint_checks_total = Counter(
    'endpoint_checks_total',
    'Total number of endpoint health checks',
    ['watched_api_id', 'endpoint_path', 'status']
)


class EndpointHealthService:
    """Service for monitoring endpoint health."""

    def __init__(self, db: Session):
        self.db = db

    async def check_endpoints(self, watched_api: WatchedAPI, spec_content: str):
        """
        Check health of all endpoints in the API spec.
        
        Args:
            watched_api: The WatchedAPI to check
            spec_content: The OpenAPI spec content (YAML/JSON string)
        
        Returns:
            Dict with summary of health checks
        """
        with tracer.start_as_current_span("health.check_all_endpoints") as span:
            span.set_attribute("watched_api.id", str(watched_api.id))
            
            logger.info(f"Checking endpoint health for {watched_api.spec_url}")
            
            # Parse spec to get endpoints
            endpoints = self._extract_endpoints(spec_content, watched_api.spec_url)
            
            if not endpoints:
                logger.warning(f"No endpoints found in spec: {watched_api.spec_url}")
                return {
                    "total": 0,
                    "healthy": 0,
                    "unhealthy": 0,
                    "endpoints": []
                }
            
            logger.info(f"Found {len(endpoints)} endpoints to check")
            
            results = {
                "total": len(endpoints),
                "healthy": 0,
                "unhealthy": 0,
                "endpoints": []
            }
            
            # Check each endpoint
            for endpoint in endpoints:
                health_result = await self._check_single_endpoint(
                    watched_api,
                    endpoint['path'],
                    endpoint['method'],
                    endpoint['base_url']
                )
                
                results["endpoints"].append(health_result)
                
                if health_result["is_healthy"]:
                    results["healthy"] += 1
                else:
                    results["unhealthy"] += 1
            
            logger.info(
                f"Health check complete: {results['healthy']} healthy, "
                f"{results['unhealthy']} unhealthy"
            )
            
            return results

    async def _check_single_endpoint(
        self,
        watched_api: WatchedAPI,
        endpoint_path: str,
        http_method: str,
        base_url: str
    ) -> Dict[str, Any]:
        """
        Check health of a single endpoint.
        
        Args:
            watched_api: The WatchedAPI being checked
            endpoint_path: The endpoint path (e.g., /v1/users)
            http_method: HTTP method (GET, POST, etc.)
            base_url: Base URL of the API
        
        Returns:
            Dict with health check result
        """
        with tracer.start_as_current_span("health.check_endpoint") as span:
            span.set_attribute("endpoint.path", endpoint_path)
            span.set_attribute("endpoint.method", http_method)
            
            full_url = f"{base_url}{endpoint_path}"
            
            start_time = datetime.now()
            status_code = None
            is_healthy = False
            error_message = None
            response_time_ms = None
            
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    # Make the request
                    if http_method.upper() == "GET":
                        response = await client.get(full_url, follow_redirects=True)
                    elif http_method.upper() == "POST":
                        response = await client.post(full_url, json={})
                    elif http_method.upper() == "PUT":
                        response = await client.put(full_url, json={})
                    elif http_method.upper() == "DELETE":
                        response = await client.delete(full_url)
                    else:
                        # For other methods, just try HEAD
                        response = await client.head(full_url)
                    
                    status_code = response.status_code
                    
                    # Consider 2xx and 3xx as healthy
                    # 4xx might be expected (auth required, etc.)
                    # Only 5xx is definitely unhealthy
                    is_healthy = 200 <= status_code < 500
                    
                    end_time = datetime.now()
                    response_time_ms = int((end_time - start_time).total_seconds() * 1000)
                    
                    logger.debug(
                        f"{http_method} {endpoint_path} returned {status_code} "
                        f"in {response_time_ms}ms"
                    )
                    
            except httpx.TimeoutException:
                error_message = "Request timeout"
                logger.warning(f"{http_method} {endpoint_path} timed out")
                
            except httpx.ConnectError as e:
                error_message = f"Connection error: {str(e)}"
                logger.warning(f"{http_method} {endpoint_path} connection failed")
                
            except Exception as e:
                error_message = str(e)
                logger.error(
                    f"Error checking {http_method} {endpoint_path}: {error_message}"
                )
            
            # Record in database
            health_record = EndpointHealth(
                watched_api_id=watched_api.id,
                endpoint_path=endpoint_path,
                http_method=http_method.upper(),
                status_code=status_code,
                response_time_ms=response_time_ms,
                is_healthy=is_healthy,
                error_message=error_message
            )
            
            self.db.add(health_record)
            self.db.commit()
            
            # Update metrics
            endpoint_health_status.labels(
                watched_api_id=str(watched_api.id),
                endpoint_path=endpoint_path,
                http_method=http_method.upper()
            ).set(1 if is_healthy else 0)
            
            if response_time_ms:
                endpoint_response_time_seconds.labels(
                    watched_api_id=str(watched_api.id),
                    endpoint_path=endpoint_path,
                    http_method=http_method.upper()
                ).observe(response_time_ms / 1000.0)
            
            endpoint_checks_total.labels(
                watched_api_id=str(watched_api.id),
                endpoint_path=endpoint_path,
                status="healthy" if is_healthy else "unhealthy"
            ).inc()
            
            # Check if this is a new failure and send alert
            if not is_healthy:
                await self._check_and_alert_failure(
                    watched_api,
                    endpoint_path,
                    http_method.upper(),
                    status_code,
                    error_message
                )
            
            return {
                "endpoint_path": endpoint_path,
                "http_method": http_method.upper(),
                "status_code": status_code,
                "response_time_ms": response_time_ms,
                "is_healthy": is_healthy,
                "error_message": error_message
            }

    def _extract_endpoints(self, spec_content: str, spec_url: str) -> List[Dict[str, str]]:
        """
        Extract endpoints from OpenAPI spec.
        
        Args:
            spec_content: The OpenAPI spec as string
            spec_url: The URL where spec was fetched (to derive base URL)
        
        Returns:
            List of dicts with path, method, base_url
        """
        import yaml
        import json
        
        try:
            # Try parsing as YAML first
            try:
                spec = yaml.safe_load(spec_content)
            except:
                # Fall back to JSON
                spec = json.loads(spec_content)
            
            # Get base URL from spec or infer from spec_url
            base_url = self._get_base_url(spec, spec_url)
            
            endpoints = []
            
            # Extract paths from spec
            paths = spec.get('paths', {})
            
            for path, path_item in paths.items():
                for method in ['get', 'post', 'put', 'delete', 'patch', 'head', 'options']:
                    if method in path_item:
                        endpoints.append({
                            'path': path,
                            'method': method.upper(),
                            'base_url': base_url
                        })
            
            # Limit to first 20 endpoints for now (avoid overwhelming)
            return endpoints[:20]
            
        except Exception as e:
            logger.error(f"Failed to parse spec for endpoints: {e}")
            return []

    def _get_base_url(self, spec: Dict, spec_url: str) -> str:
        """
        Get base URL from OpenAPI spec or infer from spec URL.
        
        Args:
            spec: Parsed OpenAPI spec dict
            spec_url: URL where spec was fetched
        
        Returns:
            Base URL for API endpoints
        """
        # OpenAPI 3.x uses 'servers'
        if 'servers' in spec and len(spec['servers']) > 0:
            return spec['servers'][0]['url']
        
        # Swagger 2.x uses 'host' and 'basePath'
        if 'host' in spec:
            scheme = spec.get('schemes', ['https'])[0]
            host = spec['host']
            base_path = spec.get('basePath', '')
            return f"{scheme}://{host}{base_path}"
        
        # Fall back to inferring from spec URL
        # e.g., https://api.stripe.com/openapi.yaml -> https://api.stripe.com
        from urllib.parse import urlparse
        parsed = urlparse(spec_url)
        return f"{parsed.scheme}://{parsed.netloc}"

    async def _check_and_alert_failure(
        self,
        watched_api: WatchedAPI,
        endpoint_path: str,
        http_method: str,
        status_code: Optional[int],
        error_message: Optional[str]
    ):
        """
        Check if endpoint just started failing and send alert.
        
        Only alerts on NEW failures (was healthy before, now unhealthy).
        
        Args:
            watched_api: The WatchedAPI
            endpoint_path: Endpoint that failed
            http_method: HTTP method
            status_code: Status code (if any)
            error_message: Error message
        """
        # Check if this endpoint was healthy in the last check
        last_check = self.db.query(EndpointHealth).filter(
            EndpointHealth.watched_api_id == watched_api.id,
            EndpointHealth.endpoint_path == endpoint_path,
            EndpointHealth.http_method == http_method,
            EndpointHealth.checked_at < datetime.now() - timedelta(seconds=10)
        ).order_by(EndpointHealth.checked_at.desc()).first()
        
        # If no previous check, or previous check was healthy, send alert
        if not last_check or last_check.is_healthy:
            logger.warning(
                f"Endpoint failure detected: {http_method} {endpoint_path} "
                f"(status: {status_code})"
            )
            
            alert_service = AlertService(self.db)
            await alert_service.send_endpoint_failure_alert(
                watched_api=watched_api,
                endpoint_path=endpoint_path,
                http_method=http_method,
                status_code=status_code or 0,
                error_message=error_message
            )