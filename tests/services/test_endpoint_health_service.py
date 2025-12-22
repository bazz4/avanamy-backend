"""
Unit tests for EndpointHealthService.

Tests endpoint health monitoring, spec parsing, HTTP requests,
and alert triggering for failed endpoints.
"""
import pytest
import uuid
from unittest.mock import MagicMock, AsyncMock, patch, call
import httpx
from datetime import datetime, timedelta

from avanamy.services.endpoint_health_service import EndpointHealthService
from avanamy.models.watched_api import WatchedAPI
from avanamy.models.endpoint_health import EndpointHealth
from avanamy.models.tenant import Tenant
from avanamy.models.provider import Provider
from avanamy.models.api_product import ApiProduct

# Configure anyio for async tests
pytestmark = pytest.mark.anyio


@pytest.fixture
def watched_api(db, tenant_provider_product):
    """Create a test WatchedAPI."""
    tenant, provider, product = tenant_provider_product
    api = WatchedAPI(
        tenant_id=tenant.id,
        provider_id=provider.id,
        api_product_id=product.id,
        spec_url="https://api.example.com/openapi.yaml",
        polling_enabled=True,
        status="active"
    )
    db.add(api)
    db.commit()
    db.refresh(api)
    return api


class TestExtractEndpoints:
    """Tests for _extract_endpoints method."""

    def test_extract_endpoints_openapi3(self, db, watched_api):
        """Test extracting endpoints from OpenAPI 3.x spec."""
        service = EndpointHealthService(db)

        spec_content = """
openapi: 3.0.0
info:
  title: Test API
  version: 1.0.0
servers:
  - url: https://api.example.com/v1
paths:
  /users:
    get:
      summary: List users
    post:
      summary: Create user
  /users/{id}:
    get:
      summary: Get user
    delete:
      summary: Delete user
"""

        endpoints = service._extract_endpoints(spec_content, watched_api.spec_url)

        assert len(endpoints) == 4
        assert {"path": "/users", "method": "GET", "base_url": "https://api.example.com/v1"} in endpoints
        assert {"path": "/users", "method": "POST", "base_url": "https://api.example.com/v1"} in endpoints
        assert {"path": "/users/{id}", "method": "GET", "base_url": "https://api.example.com/v1"} in endpoints
        assert {"path": "/users/{id}", "method": "DELETE", "base_url": "https://api.example.com/v1"} in endpoints

    def test_extract_endpoints_swagger2(self, db, watched_api):
        """Test extracting endpoints from Swagger 2.0 spec."""
        service = EndpointHealthService(db)

        spec_content = """
swagger: "2.0"
info:
  title: Test API
  version: 1.0.0
host: api.example.com
basePath: /v2
schemes:
  - https
paths:
  /products:
    get:
      summary: List products
"""

        endpoints = service._extract_endpoints(spec_content, watched_api.spec_url)

        assert len(endpoints) == 1
        assert endpoints[0] == {
            "path": "/products",
            "method": "GET",
            "base_url": "https://api.example.com/v2"
        }

    def test_extract_endpoints_no_servers_infers_from_url(self, db, watched_api):
        """Test that base URL is inferred from spec_url when not in spec."""
        service = EndpointHealthService(db)

        spec_content = """
openapi: 3.0.0
paths:
  /test:
    get:
      summary: Test endpoint
"""

        endpoints = service._extract_endpoints(spec_content, "https://api.example.com/spec.yaml")

        assert len(endpoints) == 1
        assert endpoints[0]["base_url"] == "https://api.example.com"

    def test_extract_endpoints_limits_to_20(self, db, watched_api):
        """Test that extraction limits to first 20 endpoints."""
        service = EndpointHealthService(db)

        # Generate spec with 30 endpoints
        paths = {}
        for i in range(30):
            paths[f"/endpoint{i}"] = {"get": {"summary": f"Endpoint {i}"}}

        import yaml
        spec_dict = {
            "openapi": "3.0.0",
            "paths": paths,
            "servers": [{"url": "https://api.example.com"}]
        }
        spec_content = yaml.dump(spec_dict)

        endpoints = service._extract_endpoints(spec_content, watched_api.spec_url)

        assert len(endpoints) == 20

    def test_extract_endpoints_invalid_spec(self, db, watched_api):
        """Test handling of invalid spec content."""
        service = EndpointHealthService(db)

        spec_content = "this is not valid YAML or JSON {{{{"

        endpoints = service._extract_endpoints(spec_content, watched_api.spec_url)

        assert endpoints == []


class TestGetBaseUrl:
    """Tests for _get_base_url method."""

    def test_get_base_url_from_openapi3_servers(self, db):
        """Test extracting base URL from OpenAPI 3.x servers."""
        service = EndpointHealthService(db)

        spec = {
            "openapi": "3.0.0",
            "servers": [
                {"url": "https://api.example.com/v1"},
                {"url": "https://api-staging.example.com/v1"}
            ]
        }

        base_url = service._get_base_url(spec, "https://example.com/spec.yaml")

        assert base_url == "https://api.example.com/v1"

    def test_get_base_url_from_swagger2_host(self, db):
        """Test extracting base URL from Swagger 2.0 host."""
        service = EndpointHealthService(db)

        spec = {
            "swagger": "2.0",
            "host": "api.example.com",
            "basePath": "/v2",
            "schemes": ["https"]
        }

        base_url = service._get_base_url(spec, "https://example.com/spec.yaml")

        assert base_url == "https://api.example.com/v2"

    def test_get_base_url_swagger2_no_basepath(self, db):
        """Test Swagger 2.0 without basePath."""
        service = EndpointHealthService(db)

        spec = {
            "swagger": "2.0",
            "host": "api.example.com",
            "schemes": ["https"]
        }

        base_url = service._get_base_url(spec, "https://example.com/spec.yaml")

        assert base_url == "https://api.example.com"

    def test_get_base_url_inferred_from_spec_url(self, db):
        """Test inferring base URL from spec URL."""
        service = EndpointHealthService(db)

        spec = {}  # No servers or host

        base_url = service._get_base_url(spec, "https://api.stripe.com/v1/openapi.yaml")

        assert base_url == "https://api.stripe.com"


class TestCheckSingleEndpoint:
    """Tests for _check_single_endpoint method."""

    async def test_check_single_endpoint_success_200(self, db, watched_api):
        """Test successful health check with 200 response."""
        service = EndpointHealthService(db)

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_response = AsyncMock()
            mock_response.status_code = 200
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client_class.return_value.__aenter__.return_value = mock_client

            result = await service._check_single_endpoint(
                watched_api,
                "/users",
                "GET",
                "https://api.example.com"
            )

            assert result["endpoint_path"] == "/users"
            assert result["http_method"] == "GET"
            assert result["status_code"] == 200
            assert result["is_healthy"] is True
            assert result["error_message"] is None
            assert result["response_time_ms"] is not None
            assert result["response_time_ms"] >= 0  # Can be 0 for mocked fast requests

        # Verify health record was created
        health_record = db.query(EndpointHealth).filter(
            EndpointHealth.watched_api_id == watched_api.id,
            EndpointHealth.endpoint_path == "/users"
        ).first()

        assert health_record is not None
        assert health_record.status_code == 200
        assert health_record.is_healthy is True

    async def test_check_single_endpoint_4xx_still_healthy(self, db, watched_api):
        """Test that 4xx responses (auth required) are considered healthy."""
        service = EndpointHealthService(db)

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_response = AsyncMock()
            mock_response.status_code = 401
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client_class.return_value.__aenter__.return_value = mock_client

            result = await service._check_single_endpoint(
                watched_api,
                "/protected",
                "GET",
                "https://api.example.com"
            )

            # 4xx is healthy (endpoint exists, just requires auth)
            assert result["status_code"] == 401
            assert result["is_healthy"] is True

    async def test_check_single_endpoint_5xx_unhealthy(self, db, watched_api):
        """Test that 5xx responses are unhealthy."""
        service = EndpointHealthService(db)

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_response = AsyncMock()
            mock_response.status_code = 500
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client_class.return_value.__aenter__.return_value = mock_client

            with patch.object(service, "_check_and_alert_failure", new_callable=AsyncMock) as mock_alert:
                result = await service._check_single_endpoint(
                    watched_api,
                    "/broken",
                    "GET",
                    "https://api.example.com"
                )

                assert result["status_code"] == 500
                assert result["is_healthy"] is False

                # Should trigger alert
                mock_alert.assert_called_once()

    async def test_check_single_endpoint_timeout(self, db, watched_api):
        """Test handling of request timeout."""
        service = EndpointHealthService(db)

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(side_effect=httpx.TimeoutException("Timeout"))
            mock_client_class.return_value.__aenter__.return_value = mock_client

            with patch.object(service, "_check_and_alert_failure", new_callable=AsyncMock) as mock_alert:
                result = await service._check_single_endpoint(
                    watched_api,
                    "/slow",
                    "GET",
                    "https://api.example.com"
                )

                assert result["is_healthy"] is False
                assert result["status_code"] is None
                assert result["error_message"] == "Request timeout"
                assert result["response_time_ms"] is None

                # Should trigger alert
                mock_alert.assert_called_once()

    async def test_check_single_endpoint_connection_error(self, db, watched_api):
        """Test handling of connection error."""
        service = EndpointHealthService(db)

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(
                side_effect=httpx.ConnectError("Connection refused")
            )
            mock_client_class.return_value.__aenter__.return_value = mock_client

            with patch.object(service, "_check_and_alert_failure", new_callable=AsyncMock):
                result = await service._check_single_endpoint(
                    watched_api,
                    "/unreachable",
                    "GET",
                    "https://api.example.com"
                )

                assert result["is_healthy"] is False
                assert "Connection error" in result["error_message"]

    async def test_check_single_endpoint_post_method(self, db, watched_api):
        """Test POST request handling."""
        service = EndpointHealthService(db)

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_response = AsyncMock()
            mock_response.status_code = 201
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value.__aenter__.return_value = mock_client

            result = await service._check_single_endpoint(
                watched_api,
                "/users",
                "POST",
                "https://api.example.com"
            )

            mock_client.post.assert_called_once_with(
                "https://api.example.com/users",
                json={}
            )
            assert result["http_method"] == "POST"
            assert result["is_healthy"] is True


class TestCheckEndpoints:
    """Tests for check_endpoints method."""

    async def test_check_endpoints_success(self, db, watched_api):
        """Test checking all endpoints successfully."""
        service = EndpointHealthService(db)

        spec_content = """
openapi: 3.0.0
servers:
  - url: https://api.example.com
paths:
  /users:
    get:
      summary: List users
  /products:
    get:
      summary: List products
"""

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_response = AsyncMock()
            mock_response.status_code = 200
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client_class.return_value.__aenter__.return_value = mock_client

            result = await service.check_endpoints(watched_api, spec_content)

            assert result["total"] == 2
            assert result["healthy"] == 2
            assert result["unhealthy"] == 0
            assert len(result["endpoints"]) == 2

    async def test_check_endpoints_mixed_results(self, db, watched_api):
        """Test with mix of healthy and unhealthy endpoints."""
        service = EndpointHealthService(db)

        spec_content = """
openapi: 3.0.0
servers:
  - url: https://api.example.com
paths:
  /healthy:
    get:
      summary: Healthy endpoint
  /broken:
    get:
      summary: Broken endpoint
"""

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()

            # First call returns 200, second returns 500
            mock_response_ok = AsyncMock()
            mock_response_ok.status_code = 200
            mock_response_error = AsyncMock()
            mock_response_error.status_code = 500

            mock_client.get = AsyncMock(side_effect=[mock_response_ok, mock_response_error])
            mock_client_class.return_value.__aenter__.return_value = mock_client

            with patch.object(service, "_check_and_alert_failure", new_callable=AsyncMock):
                result = await service.check_endpoints(watched_api, spec_content)

                assert result["total"] == 2
                assert result["healthy"] == 1
                assert result["unhealthy"] == 1

    async def test_check_endpoints_no_endpoints_found(self, db, watched_api):
        """Test when spec has no endpoints."""
        service = EndpointHealthService(db)

        spec_content = """
openapi: 3.0.0
info:
  title: Empty API
paths: {}
"""

        result = await service.check_endpoints(watched_api, spec_content)

        assert result["total"] == 0
        assert result["healthy"] == 0
        assert result["unhealthy"] == 0
        assert result["endpoints"] == []


class TestCheckAndAlertFailure:
    """Tests for _check_and_alert_failure method."""

    async def test_alert_on_new_failure(self, db, watched_api):
        """Test that alert is sent when endpoint starts failing."""
        service = EndpointHealthService(db)

        # Create a previous healthy check
        previous_check = EndpointHealth(
            watched_api_id=watched_api.id,
            endpoint_path="/users",
            http_method="GET",
            status_code=200,
            response_time_ms=100,
            is_healthy=True
        )
        db.add(previous_check)
        db.commit()

        # Make previous check older
        previous_check.checked_at = datetime.now() - timedelta(minutes=5)
        db.commit()

        with patch("avanamy.services.endpoint_health_service.AlertService") as mock_alert_service_class:
            mock_alert_service = AsyncMock()
            mock_alert_service_class.return_value = mock_alert_service

            await service._check_and_alert_failure(
                watched_api,
                "/users",
                "GET",
                500,
                "Internal Server Error"
            )

            # Alert should be sent
            mock_alert_service.send_endpoint_failure_alert.assert_called_once_with(
                watched_api=watched_api,
                endpoint_path="/users",
                http_method="GET",
                status_code=500,
                error_message="Internal Server Error"
            )

    async def test_no_alert_if_already_failing(self, db, watched_api):
        """Test that alert is NOT sent if endpoint was already failing."""
        service = EndpointHealthService(db)

        # Create a previous unhealthy check
        previous_check = EndpointHealth(
            watched_api_id=watched_api.id,
            endpoint_path="/broken",
            http_method="GET",
            status_code=500,
            response_time_ms=None,
            is_healthy=False,
            error_message="Previous error"
        )
        db.add(previous_check)
        db.commit()

        # Make previous check older
        previous_check.checked_at = datetime.now() - timedelta(minutes=5)
        db.commit()

        with patch("avanamy.services.endpoint_health_service.AlertService") as mock_alert_service_class:
            mock_alert_service = AsyncMock()
            mock_alert_service_class.return_value = mock_alert_service

            await service._check_and_alert_failure(
                watched_api,
                "/broken",
                "GET",
                500,
                "Still broken"
            )

            # No alert should be sent (already failing)
            mock_alert_service.send_endpoint_failure_alert.assert_not_called()

    async def test_alert_on_first_failure_no_previous_check(self, db, watched_api):
        """Test that alert is sent on first failure (no previous check)."""
        service = EndpointHealthService(db)

        with patch("avanamy.services.endpoint_health_service.AlertService") as mock_alert_service_class:
            mock_alert_service = AsyncMock()
            mock_alert_service_class.return_value = mock_alert_service

            await service._check_and_alert_failure(
                watched_api,
                "/new-endpoint",
                "POST",
                503,
                "Service unavailable"
            )

            # Alert should be sent (first check and it's failing)
            mock_alert_service.send_endpoint_failure_alert.assert_called_once()
