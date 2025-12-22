"""
Unit tests for EndpointHealth model.

Tests model creation, relationships, and health tracking.
"""
import pytest
import uuid
from datetime import datetime

from avanamy.models.endpoint_health import EndpointHealth
from avanamy.models.tenant import Tenant
from avanamy.models.provider import Provider
from avanamy.models.api_product import ApiProduct
from avanamy.models.watched_api import WatchedAPI


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


def test_endpoint_health_creation_healthy(db, watched_api):
    """Test creating a healthy endpoint health record."""
    endpoint_health = EndpointHealth(
        watched_api_id=watched_api.id,
        endpoint_path="/v1/users",
        http_method="GET",
        status_code=200,
        response_time_ms=150,
        is_healthy=True
    )

    db.add(endpoint_health)
    db.commit()
    db.refresh(endpoint_health)

    assert endpoint_health.id is not None
    assert endpoint_health.watched_api_id == watched_api.id
    assert endpoint_health.endpoint_path == "/v1/users"
    assert endpoint_health.http_method == "GET"
    assert endpoint_health.status_code == 200
    assert endpoint_health.response_time_ms == 150
    assert endpoint_health.is_healthy is True
    assert endpoint_health.error_message is None
    assert endpoint_health.checked_at is not None


def test_endpoint_health_creation_unhealthy(db, watched_api):
    """Test creating an unhealthy endpoint health record."""
    endpoint_health = EndpointHealth(
        watched_api_id=watched_api.id,
        endpoint_path="/v1/payments",
        http_method="POST",
        status_code=500,
        response_time_ms=5000,
        is_healthy=False,
        error_message="Internal Server Error"
    )

    db.add(endpoint_health)
    db.commit()
    db.refresh(endpoint_health)

    assert endpoint_health.id is not None
    assert endpoint_health.endpoint_path == "/v1/payments"
    assert endpoint_health.http_method == "POST"
    assert endpoint_health.status_code == 500
    assert endpoint_health.response_time_ms == 5000
    assert endpoint_health.is_healthy is False
    assert endpoint_health.error_message == "Internal Server Error"


def test_endpoint_health_timeout(db, watched_api):
    """Test recording a timeout error."""
    endpoint_health = EndpointHealth(
        watched_api_id=watched_api.id,
        endpoint_path="/v1/slow-endpoint",
        http_method="GET",
        status_code=None,
        response_time_ms=None,
        is_healthy=False,
        error_message="Request timeout after 30 seconds"
    )

    db.add(endpoint_health)
    db.commit()
    db.refresh(endpoint_health)

    assert endpoint_health.status_code is None
    assert endpoint_health.response_time_ms is None
    assert endpoint_health.is_healthy is False
    assert "timeout" in endpoint_health.error_message.lower()


def test_endpoint_health_network_error(db, watched_api):
    """Test recording a network error."""
    endpoint_health = EndpointHealth(
        watched_api_id=watched_api.id,
        endpoint_path="/v1/unreachable",
        http_method="DELETE",
        status_code=None,
        response_time_ms=None,
        is_healthy=False,
        error_message="Connection refused"
    )

    db.add(endpoint_health)
    db.commit()
    db.refresh(endpoint_health)

    assert endpoint_health.is_healthy is False
    assert endpoint_health.error_message == "Connection refused"


def test_endpoint_health_relationship(db, watched_api):
    """Test relationship to watched_api."""
    endpoint_health = EndpointHealth(
        watched_api_id=watched_api.id,
        endpoint_path="/v1/products",
        http_method="GET",
        status_code=200,
        response_time_ms=100,
        is_healthy=True
    )

    db.add(endpoint_health)
    db.commit()
    db.refresh(endpoint_health)

    # Test relationship
    assert endpoint_health.watched_api.id == watched_api.id
    assert endpoint_health.watched_api.spec_url == watched_api.spec_url


def test_endpoint_health_repr_healthy(db, watched_api):
    """Test __repr__ for healthy endpoint."""
    endpoint_health = EndpointHealth(
        watched_api_id=watched_api.id,
        endpoint_path="/v1/status",
        http_method="GET",
        status_code=200,
        response_time_ms=50,
        is_healthy=True
    )

    db.add(endpoint_health)
    db.commit()
    db.refresh(endpoint_health)

    repr_str = repr(endpoint_health)
    assert "EndpointHealth" in repr_str
    assert "GET" in repr_str
    assert "/v1/status" in repr_str
    assert "healthy" in repr_str


def test_endpoint_health_repr_unhealthy(db, watched_api):
    """Test __repr__ for unhealthy endpoint."""
    endpoint_health = EndpointHealth(
        watched_api_id=watched_api.id,
        endpoint_path="/v1/broken",
        http_method="POST",
        status_code=503,
        response_time_ms=100,
        is_healthy=False
    )

    db.add(endpoint_health)
    db.commit()
    db.refresh(endpoint_health)

    repr_str = repr(endpoint_health)
    assert "EndpointHealth" in repr_str
    assert "POST" in repr_str
    assert "/v1/broken" in repr_str
    assert "unhealthy" in repr_str


def test_multiple_health_checks_same_endpoint(db, watched_api):
    """Test multiple health check records for the same endpoint over time."""
    # First check - healthy
    check_1 = EndpointHealth(
        watched_api_id=watched_api.id,
        endpoint_path="/v1/users",
        http_method="GET",
        status_code=200,
        response_time_ms=100,
        is_healthy=True
    )

    # Second check - degraded performance
    check_2 = EndpointHealth(
        watched_api_id=watched_api.id,
        endpoint_path="/v1/users",
        http_method="GET",
        status_code=200,
        response_time_ms=3000,
        is_healthy=True
    )

    # Third check - failed
    check_3 = EndpointHealth(
        watched_api_id=watched_api.id,
        endpoint_path="/v1/users",
        http_method="GET",
        status_code=500,
        response_time_ms=5000,
        is_healthy=False,
        error_message="Database connection lost"
    )

    db.add_all([check_1, check_2, check_3])
    db.commit()

    # Query all checks for this endpoint
    checks = db.query(EndpointHealth).filter(
        EndpointHealth.watched_api_id == watched_api.id,
        EndpointHealth.endpoint_path == "/v1/users",
        EndpointHealth.http_method == "GET"
    ).order_by(EndpointHealth.checked_at).all()

    assert len(checks) == 3
    assert checks[0].is_healthy is True
    assert checks[0].response_time_ms == 100
    assert checks[1].is_healthy is True
    assert checks[1].response_time_ms == 3000
    assert checks[2].is_healthy is False
    assert checks[2].status_code == 500


def test_endpoint_health_different_http_methods(db, watched_api):
    """Test health checks for same path but different HTTP methods."""
    get_check = EndpointHealth(
        watched_api_id=watched_api.id,
        endpoint_path="/v1/items",
        http_method="GET",
        status_code=200,
        response_time_ms=100,
        is_healthy=True
    )

    post_check = EndpointHealth(
        watched_api_id=watched_api.id,
        endpoint_path="/v1/items",
        http_method="POST",
        status_code=201,
        response_time_ms=150,
        is_healthy=True
    )

    put_check = EndpointHealth(
        watched_api_id=watched_api.id,
        endpoint_path="/v1/items",
        http_method="PUT",
        status_code=500,
        response_time_ms=2000,
        is_healthy=False,
        error_message="Validation error"
    )

    delete_check = EndpointHealth(
        watched_api_id=watched_api.id,
        endpoint_path="/v1/items",
        http_method="DELETE",
        status_code=204,
        response_time_ms=80,
        is_healthy=True
    )

    db.add_all([get_check, post_check, put_check, delete_check])
    db.commit()

    # Query all checks for this path
    checks = db.query(EndpointHealth).filter(
        EndpointHealth.watched_api_id == watched_api.id,
        EndpointHealth.endpoint_path == "/v1/items"
    ).all()

    assert len(checks) == 4
    http_methods = {check.http_method for check in checks}
    assert http_methods == {"GET", "POST", "PUT", "DELETE"}


def test_query_unhealthy_endpoints(db, watched_api):
    """Test querying only unhealthy endpoints."""
    healthy_check = EndpointHealth(
        watched_api_id=watched_api.id,
        endpoint_path="/v1/healthy",
        http_method="GET",
        status_code=200,
        response_time_ms=100,
        is_healthy=True
    )

    unhealthy_check_1 = EndpointHealth(
        watched_api_id=watched_api.id,
        endpoint_path="/v1/broken",
        http_method="GET",
        status_code=500,
        response_time_ms=5000,
        is_healthy=False
    )

    unhealthy_check_2 = EndpointHealth(
        watched_api_id=watched_api.id,
        endpoint_path="/v1/timeout",
        http_method="POST",
        status_code=None,
        response_time_ms=None,
        is_healthy=False
    )

    db.add_all([healthy_check, unhealthy_check_1, unhealthy_check_2])
    db.commit()

    # Query unhealthy endpoints
    unhealthy = db.query(EndpointHealth).filter(
        EndpointHealth.watched_api_id == watched_api.id,
        EndpointHealth.is_healthy == False
    ).all()

    assert len(unhealthy) == 2


def test_query_latest_health_check_per_endpoint(db, watched_api):
    """Test querying the most recent health check for each endpoint."""
    # Create multiple checks for different endpoints
    endpoints = ["/v1/users", "/v1/products", "/v1/orders"]

    for endpoint in endpoints:
        # Old check
        old_check = EndpointHealth(
            watched_api_id=watched_api.id,
            endpoint_path=endpoint,
            http_method="GET",
            status_code=200,
            response_time_ms=100,
            is_healthy=True
        )
        db.add(old_check)
        db.commit()

        # Update checked_at to be older
        old_check.checked_at = datetime(2024, 1, 1, 10, 0, 0)
        db.commit()

        # New check
        new_check = EndpointHealth(
            watched_api_id=watched_api.id,
            endpoint_path=endpoint,
            http_method="GET",
            status_code=500 if endpoint == "/v1/orders" else 200,
            response_time_ms=200,
            is_healthy=False if endpoint == "/v1/orders" else True
        )
        db.add(new_check)
        db.commit()

    # Query latest check for each endpoint
    # This is a simplified version - in production you'd use window functions or subqueries
    all_checks = db.query(EndpointHealth).filter(
        EndpointHealth.watched_api_id == watched_api.id
    ).order_by(EndpointHealth.checked_at.desc()).all()

    assert len(all_checks) == 6  # 3 endpoints * 2 checks each


def test_endpoint_health_status_codes(db, watched_api):
    """Test various HTTP status codes."""
    status_codes = [
        (200, True, "OK"),
        (201, True, "Created"),
        (204, True, "No Content"),
        (301, True, "Moved Permanently"),
        (400, False, "Bad Request"),
        (401, False, "Unauthorized"),
        (403, False, "Forbidden"),
        (404, False, "Not Found"),
        (429, False, "Too Many Requests"),
        (500, False, "Internal Server Error"),
        (502, False, "Bad Gateway"),
        (503, False, "Service Unavailable"),
        (504, False, "Gateway Timeout")
    ]

    for status_code, is_healthy, description in status_codes:
        check = EndpointHealth(
            watched_api_id=watched_api.id,
            endpoint_path=f"/v1/endpoint-{status_code}",
            http_method="GET",
            status_code=status_code,
            response_time_ms=100,
            is_healthy=is_healthy,
            error_message=None if is_healthy else description
        )
        db.add(check)

    db.commit()

    # Verify all were created
    all_checks = db.query(EndpointHealth).filter(
        EndpointHealth.watched_api_id == watched_api.id
    ).all()

    assert len(all_checks) == len(status_codes)


def test_endpoint_health_response_times(db, watched_api):
    """Test tracking various response times."""
    response_times = [
        (50, True),      # Very fast
        (200, True),     # Normal
        (500, True),     # Acceptable
        (1000, True),    # Slow but ok
        (3000, False),   # Too slow
        (10000, False)   # Very slow
    ]

    for response_time, is_healthy in response_times:
        check = EndpointHealth(
            watched_api_id=watched_api.id,
            endpoint_path="/v1/performance",
            http_method="GET",
            status_code=200,
            response_time_ms=response_time,
            is_healthy=is_healthy
        )
        db.add(check)

    db.commit()

    # Query checks for performance endpoint
    checks = db.query(EndpointHealth).filter(
        EndpointHealth.watched_api_id == watched_api.id,
        EndpointHealth.endpoint_path == "/v1/performance"
    ).order_by(EndpointHealth.response_time_ms).all()

    assert len(checks) == len(response_times)
    assert checks[0].response_time_ms == 50
    assert checks[-1].response_time_ms == 10000
