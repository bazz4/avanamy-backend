"""
Unit tests for WatchedAPI model.

Tests model creation, relationships, and field validation.
"""
import pytest
import uuid
from datetime import datetime

from avanamy.models.watched_api import WatchedAPI
from avanamy.models.tenant import Tenant
from avanamy.models.provider import Provider
from avanamy.models.api_product import ApiProduct


def test_watched_api_creation(db, tenant_provider_product):
    """Test creating a basic WatchedAPI instance."""
    tenant, provider, product = tenant_provider_product

    watched_api = WatchedAPI(
        tenant_id=tenant.id,
        provider_id=provider.id,
        api_product_id=product.id,
        spec_url="https://api.stripe.com/openapi.yaml",
        polling_frequency="daily",
        polling_enabled=True,
        status="active"
    )

    db.add(watched_api)
    db.commit()
    db.refresh(watched_api)

    assert watched_api.id is not None
    assert watched_api.tenant_id == tenant.id
    assert watched_api.provider_id == provider.id
    assert watched_api.api_product_id == product.id
    assert watched_api.spec_url == "https://api.stripe.com/openapi.yaml"
    assert watched_api.polling_frequency == "daily"
    assert watched_api.polling_enabled is True
    assert watched_api.status == "active"
    assert watched_api.consecutive_failures == 0
    assert watched_api.created_at is not None


def test_watched_api_defaults(db, tenant_provider_product):
    """Test that default values are set correctly."""
    tenant, provider, product = tenant_provider_product

    watched_api = WatchedAPI(
        tenant_id=tenant.id,
        provider_id=provider.id,
        api_product_id=product.id,
        spec_url="https://example.com/spec.json"
    )

    db.add(watched_api)
    db.commit()
    db.refresh(watched_api)

    # Check defaults
    assert watched_api.polling_frequency == "daily"
    assert watched_api.polling_enabled is True
    assert watched_api.status == "active"
    assert watched_api.consecutive_failures == 0
    assert watched_api.last_polled_at is None
    assert watched_api.last_successful_poll_at is None
    assert watched_api.last_version_detected is None
    assert watched_api.last_spec_hash is None
    assert watched_api.last_error is None


def test_watched_api_relationships(db, tenant_provider_product):
    """Test that relationships to tenant, provider, and api_product work."""
    tenant, provider, product = tenant_provider_product

    watched_api = WatchedAPI(
        tenant_id=tenant.id,
        provider_id=provider.id,
        api_product_id=product.id,
        spec_url="https://example.com/spec.yaml"
    )

    db.add(watched_api)
    db.commit()
    db.refresh(watched_api)

    # Test relationships
    assert watched_api.tenant.id == tenant.id
    assert watched_api.tenant.name == tenant.name
    assert watched_api.provider.id == provider.id
    assert watched_api.provider.name == provider.name
    assert watched_api.api_product.id == product.id
    assert watched_api.api_product.name == product.name


def test_watched_api_tracking_fields(db, tenant_provider_product):
    """Test updating tracking fields."""
    tenant, provider, product = tenant_provider_product

    watched_api = WatchedAPI(
        tenant_id=tenant.id,
        provider_id=provider.id,
        api_product_id=product.id,
        spec_url="https://example.com/spec.yaml"
    )

    db.add(watched_api)
    db.commit()
    db.refresh(watched_api)

    # Update tracking fields
    now = datetime.now()
    watched_api.last_polled_at = now
    watched_api.last_successful_poll_at = now
    watched_api.last_version_detected = 5
    watched_api.last_spec_hash = "abc123hash"
    watched_api.consecutive_failures = 2

    db.commit()
    db.refresh(watched_api)

    assert watched_api.last_polled_at == now
    assert watched_api.last_successful_poll_at == now
    assert watched_api.last_version_detected == 5
    assert watched_api.last_spec_hash == "abc123hash"
    assert watched_api.consecutive_failures == 2


def test_watched_api_failure_tracking(db, tenant_provider_product):
    """Test tracking consecutive failures and error messages."""
    tenant, provider, product = tenant_provider_product

    watched_api = WatchedAPI(
        tenant_id=tenant.id,
        provider_id=provider.id,
        api_product_id=product.id,
        spec_url="https://example.com/spec.yaml"
    )

    db.add(watched_api)
    db.commit()
    db.refresh(watched_api)

    # Simulate failures
    watched_api.consecutive_failures = 3
    watched_api.last_error = "HTTP 404: Not Found"

    db.commit()
    db.refresh(watched_api)

    assert watched_api.consecutive_failures == 3
    assert watched_api.last_error == "HTTP 404: Not Found"


def test_watched_api_status_transitions(db, tenant_provider_product):
    """Test different status values."""
    tenant, provider, product = tenant_provider_product

    watched_api = WatchedAPI(
        tenant_id=tenant.id,
        provider_id=provider.id,
        api_product_id=product.id,
        spec_url="https://example.com/spec.yaml",
        status="active"
    )

    db.add(watched_api)
    db.commit()
    db.refresh(watched_api)

    assert watched_api.status == "active"

    # Transition to paused
    watched_api.status = "paused"
    db.commit()
    db.refresh(watched_api)
    assert watched_api.status == "paused"

    # Transition to failed
    watched_api.status = "failed"
    db.commit()
    db.refresh(watched_api)
    assert watched_api.status == "failed"

    # Transition to deleted
    watched_api.status = "deleted"
    db.commit()
    db.refresh(watched_api)
    assert watched_api.status == "deleted"


def test_watched_api_polling_enabled_toggle(db, tenant_provider_product):
    """Test toggling polling_enabled flag."""
    tenant, provider, product = tenant_provider_product

    watched_api = WatchedAPI(
        tenant_id=tenant.id,
        provider_id=provider.id,
        api_product_id=product.id,
        spec_url="https://example.com/spec.yaml",
        polling_enabled=True
    )

    db.add(watched_api)
    db.commit()
    db.refresh(watched_api)

    assert watched_api.polling_enabled is True

    # Disable polling
    watched_api.polling_enabled = False
    db.commit()
    db.refresh(watched_api)
    assert watched_api.polling_enabled is False


def test_watched_api_repr(db, tenant_provider_product):
    """Test the __repr__ method."""
    tenant, provider, product = tenant_provider_product

    watched_api = WatchedAPI(
        tenant_id=tenant.id,
        provider_id=provider.id,
        api_product_id=product.id,
        spec_url="https://example.com/spec.yaml",
        status="active"
    )

    db.add(watched_api)
    db.commit()
    db.refresh(watched_api)

    repr_str = repr(watched_api)
    assert "WatchedAPI" in repr_str
    assert str(watched_api.id) in repr_str
    assert "https://example.com/spec.yaml" in repr_str
    assert "active" in repr_str


def test_multiple_watched_apis_for_same_tenant(db, tenant_provider_product):
    """Test that a tenant can have multiple watched APIs."""
    tenant, provider, product = tenant_provider_product

    watched_api_1 = WatchedAPI(
        tenant_id=tenant.id,
        provider_id=provider.id,
        api_product_id=product.id,
        spec_url="https://api1.example.com/spec.yaml"
    )

    watched_api_2 = WatchedAPI(
        tenant_id=tenant.id,
        provider_id=provider.id,
        api_product_id=product.id,
        spec_url="https://api2.example.com/spec.yaml"
    )

    db.add_all([watched_api_1, watched_api_2])
    db.commit()

    watched_apis = db.query(WatchedAPI).filter(
        WatchedAPI.tenant_id == tenant.id
    ).all()

    assert len(watched_apis) == 2
    assert watched_apis[0].spec_url != watched_apis[1].spec_url


def test_watched_api_polling_frequency_options(db, tenant_provider_product):
    """Test different polling frequency values."""
    tenant, provider, product = tenant_provider_product

    for frequency in ["hourly", "daily", "weekly"]:
        watched_api = WatchedAPI(
            tenant_id=tenant.id,
            provider_id=provider.id,
            api_product_id=product.id,
            spec_url=f"https://example.com/{frequency}.yaml",
            polling_frequency=frequency
        )

        db.add(watched_api)
        db.commit()
        db.refresh(watched_api)

        assert watched_api.polling_frequency == frequency

        # Clean up for next iteration
        db.delete(watched_api)
        db.commit()
