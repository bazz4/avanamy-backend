"""
Unit tests for AlertConfiguration model.

Tests model creation, relationships, and field validation.
"""
import pytest
import uuid

from avanamy.models.alert_configuration import AlertConfiguration
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


def test_alert_configuration_creation_email(db, tenant_provider_product, watched_api):
    """Test creating an email alert configuration."""
    tenant, _, _ = tenant_provider_product

    alert_config = AlertConfiguration(
        tenant_id=tenant.id,
        watched_api_id=watched_api.id,
        alert_type="email",
        destination="alerts@example.com",
        alert_on_breaking_changes=True,
        alert_on_non_breaking_changes=False,
        alert_on_endpoint_failures=True,
        alert_on_endpoint_recovery=False,
        enabled=True
    )

    db.add(alert_config)
    db.commit()
    db.refresh(alert_config)

    assert alert_config.id is not None
    assert alert_config.tenant_id == tenant.id
    assert alert_config.watched_api_id == watched_api.id
    assert alert_config.alert_type == "email"
    assert alert_config.destination == "alerts@example.com"
    assert alert_config.alert_on_breaking_changes is True
    assert alert_config.alert_on_non_breaking_changes is False
    assert alert_config.alert_on_endpoint_failures is True
    assert alert_config.alert_on_endpoint_recovery is False
    assert alert_config.enabled is True
    assert alert_config.created_at is not None


def test_alert_configuration_creation_webhook(db, tenant_provider_product, watched_api):
    """Test creating a webhook alert configuration."""
    tenant, _, _ = tenant_provider_product

    alert_config = AlertConfiguration(
        tenant_id=tenant.id,
        watched_api_id=watched_api.id,
        alert_type="webhook",
        destination="https://hooks.example.com/alerts"
    )

    db.add(alert_config)
    db.commit()
    db.refresh(alert_config)

    assert alert_config.id is not None
    assert alert_config.alert_type == "webhook"
    assert alert_config.destination == "https://hooks.example.com/alerts"


def test_alert_configuration_creation_slack(db, tenant_provider_product, watched_api):
    """Test creating a Slack alert configuration."""
    tenant, _, _ = tenant_provider_product

    alert_config = AlertConfiguration(
        tenant_id=tenant.id,
        watched_api_id=watched_api.id,
        alert_type="slack",
        destination="#alerts-channel"
    )

    db.add(alert_config)
    db.commit()
    db.refresh(alert_config)

    assert alert_config.id is not None
    assert alert_config.alert_type == "slack"
    assert alert_config.destination == "#alerts-channel"


def test_alert_configuration_defaults(db, tenant_provider_product, watched_api):
    """Test that default values are set correctly."""
    tenant, _, _ = tenant_provider_product

    alert_config = AlertConfiguration(
        tenant_id=tenant.id,
        watched_api_id=watched_api.id,
        alert_type="email",
        destination="test@example.com"
    )

    db.add(alert_config)
    db.commit()
    db.refresh(alert_config)

    # Check defaults
    assert alert_config.alert_on_breaking_changes is True
    assert alert_config.alert_on_non_breaking_changes is False
    assert alert_config.alert_on_endpoint_failures is True
    assert alert_config.alert_on_endpoint_recovery is False
    assert alert_config.enabled is True
    assert alert_config.created_by_user_id is None
    assert alert_config.updated_at is None


def test_alert_configuration_relationships(db, tenant_provider_product, watched_api):
    """Test relationships to tenant and watched_api."""
    tenant, _, _ = tenant_provider_product

    alert_config = AlertConfiguration(
        tenant_id=tenant.id,
        watched_api_id=watched_api.id,
        alert_type="email",
        destination="test@example.com"
    )

    db.add(alert_config)
    db.commit()
    db.refresh(alert_config)

    # Test relationships
    assert alert_config.tenant.id == tenant.id
    assert alert_config.tenant.name == tenant.name
    assert alert_config.watched_api.id == watched_api.id
    assert alert_config.watched_api.spec_url == watched_api.spec_url


def test_alert_configuration_enabled_toggle(db, tenant_provider_product, watched_api):
    """Test toggling the enabled flag."""
    tenant, _, _ = tenant_provider_product

    alert_config = AlertConfiguration(
        tenant_id=tenant.id,
        watched_api_id=watched_api.id,
        alert_type="email",
        destination="test@example.com",
        enabled=True
    )

    db.add(alert_config)
    db.commit()
    db.refresh(alert_config)

    assert alert_config.enabled is True

    # Disable
    alert_config.enabled = False
    db.commit()
    db.refresh(alert_config)
    assert alert_config.enabled is False


def test_alert_configuration_update_triggers(db, tenant_provider_product, watched_api):
    """Test updating alert trigger settings."""
    tenant, _, _ = tenant_provider_product

    alert_config = AlertConfiguration(
        tenant_id=tenant.id,
        watched_api_id=watched_api.id,
        alert_type="email",
        destination="test@example.com",
        alert_on_breaking_changes=True,
        alert_on_non_breaking_changes=False,
        alert_on_endpoint_failures=True,
        alert_on_endpoint_recovery=False
    )

    db.add(alert_config)
    db.commit()
    db.refresh(alert_config)

    # Update triggers
    alert_config.alert_on_non_breaking_changes = True
    alert_config.alert_on_endpoint_recovery = True
    db.commit()
    db.refresh(alert_config)

    assert alert_config.alert_on_breaking_changes is True
    assert alert_config.alert_on_non_breaking_changes is True
    assert alert_config.alert_on_endpoint_failures is True
    assert alert_config.alert_on_endpoint_recovery is True


def test_alert_configuration_repr(db, tenant_provider_product, watched_api):
    """Test the __repr__ method."""
    tenant, _, _ = tenant_provider_product

    alert_config = AlertConfiguration(
        tenant_id=tenant.id,
        watched_api_id=watched_api.id,
        alert_type="webhook",
        destination="https://example.com/webhook"
    )

    db.add(alert_config)
    db.commit()
    db.refresh(alert_config)

    repr_str = repr(alert_config)
    assert "AlertConfiguration" in repr_str
    assert str(alert_config.id) in repr_str
    assert "webhook" in repr_str
    assert "https://example.com/webhook" in repr_str


def test_multiple_alert_configs_for_same_watched_api(db, tenant_provider_product, watched_api):
    """Test that a watched API can have multiple alert configurations."""
    tenant, _, _ = tenant_provider_product

    email_config = AlertConfiguration(
        tenant_id=tenant.id,
        watched_api_id=watched_api.id,
        alert_type="email",
        destination="team@example.com"
    )

    webhook_config = AlertConfiguration(
        tenant_id=tenant.id,
        watched_api_id=watched_api.id,
        alert_type="webhook",
        destination="https://hooks.example.com/alerts"
    )

    slack_config = AlertConfiguration(
        tenant_id=tenant.id,
        watched_api_id=watched_api.id,
        alert_type="slack",
        destination="#api-alerts"
    )

    db.add_all([email_config, webhook_config, slack_config])
    db.commit()

    configs = db.query(AlertConfiguration).filter(
        AlertConfiguration.watched_api_id == watched_api.id
    ).all()

    assert len(configs) == 3
    alert_types = {c.alert_type for c in configs}
    assert alert_types == {"email", "webhook", "slack"}


def test_query_enabled_alert_configs(db, tenant_provider_product, watched_api):
    """Test querying only enabled alert configurations."""
    tenant, _, _ = tenant_provider_product

    enabled_config = AlertConfiguration(
        tenant_id=tenant.id,
        watched_api_id=watched_api.id,
        alert_type="email",
        destination="enabled@example.com",
        enabled=True
    )

    disabled_config = AlertConfiguration(
        tenant_id=tenant.id,
        watched_api_id=watched_api.id,
        alert_type="email",
        destination="disabled@example.com",
        enabled=False
    )

    db.add_all([enabled_config, disabled_config])
    db.commit()

    # Query only enabled configs
    enabled_configs = db.query(AlertConfiguration).filter(
        AlertConfiguration.watched_api_id == watched_api.id,
        AlertConfiguration.enabled == True
    ).all()

    assert len(enabled_configs) == 1
    assert enabled_configs[0].destination == "enabled@example.com"


def test_query_breaking_change_alerts(db, tenant_provider_product, watched_api):
    """Test querying alert configs that trigger on breaking changes."""
    tenant, _, _ = tenant_provider_product

    breaking_config = AlertConfiguration(
        tenant_id=tenant.id,
        watched_api_id=watched_api.id,
        alert_type="email",
        destination="breaking@example.com",
        alert_on_breaking_changes=True,
        alert_on_endpoint_failures=False
    )

    endpoint_config = AlertConfiguration(
        tenant_id=tenant.id,
        watched_api_id=watched_api.id,
        alert_type="email",
        destination="endpoint@example.com",
        alert_on_breaking_changes=False,
        alert_on_endpoint_failures=True
    )

    db.add_all([breaking_config, endpoint_config])
    db.commit()

    # Query only breaking change configs
    breaking_configs = db.query(AlertConfiguration).filter(
        AlertConfiguration.watched_api_id == watched_api.id,
        AlertConfiguration.enabled == True,
        AlertConfiguration.alert_on_breaking_changes == True
    ).all()

    assert len(breaking_configs) == 1
    assert breaking_configs[0].destination == "breaking@example.com"
