"""
Unit tests for AlertHistory model.

Tests model creation, relationships, status tracking, and audit fields.
"""
import pytest
import uuid
from datetime import datetime

from avanamy.models.alert_history import AlertHistory
from avanamy.models.alert_configuration import AlertConfiguration
from avanamy.models.tenant import Tenant
from avanamy.models.provider import Provider
from avanamy.models.api_product import ApiProduct
from avanamy.models.watched_api import WatchedAPI
from avanamy.models.version_history import VersionHistory
from avanamy.models.api_spec import ApiSpec


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


@pytest.fixture
def alert_config(db, tenant_provider_product, watched_api):
    """Create a test AlertConfiguration."""
    tenant, _, _ = tenant_provider_product
    config = AlertConfiguration(
        tenant_id=tenant.id,
        watched_api_id=watched_api.id,
        alert_type="email",
        destination="test@example.com",
        enabled=True
    )
    db.add(config)
    db.commit()
    db.refresh(config)
    return config


@pytest.fixture
def version_history(db, tenant_provider_product):
    """Create a test VersionHistory record."""
    tenant, provider, product = tenant_provider_product

    # Create ApiSpec first
    spec = ApiSpec(
        tenant_id=tenant.id,
        api_product_id=product.id,
        provider_id=provider.id,
        name="Test API",
        version="v1",
        description="Test API for alerts",
        original_file_s3_path="s3://test-bucket/test-spec.yaml"
    )
    db.add(spec)
    db.commit()
    db.refresh(spec)

    # Create VersionHistory
    version = VersionHistory(
        api_spec_id=spec.id,
        version=1
    )
    db.add(version)
    db.commit()
    db.refresh(version)
    return version


def test_alert_history_creation_breaking_change(db, tenant_provider_product, watched_api, alert_config, version_history):
    """Test creating alert history for breaking change."""
    tenant, _, _ = tenant_provider_product

    payload = {
        "type": "breaking_change",
        "severity": "critical",
        "subject": "Breaking Change Detected",
        "details": {
            "api_url": "https://api.example.com/openapi.yaml",
            "version": 2,
            "change_count": 5
        }
    }

    alert_history = AlertHistory(
        tenant_id=tenant.id,
        watched_api_id=watched_api.id,
        alert_config_id=alert_config.id,
        version_history_id=version_history.id,
        alert_reason="breaking_change",
        severity="critical",
        payload=payload,
        status="pending"
    )

    db.add(alert_history)
    db.commit()
    db.refresh(alert_history)

    assert alert_history.id is not None
    assert alert_history.tenant_id == tenant.id
    assert alert_history.watched_api_id == watched_api.id
    assert alert_history.alert_config_id == alert_config.id
    assert alert_history.version_history_id == version_history.id
    assert alert_history.alert_reason == "breaking_change"
    assert alert_history.severity == "critical"
    assert alert_history.payload == payload
    assert alert_history.status == "pending"
    assert alert_history.endpoint_path is None
    assert alert_history.http_method is None
    assert alert_history.error_message is None
    assert alert_history.sent_at is None
    assert alert_history.created_at is not None


def test_alert_history_creation_endpoint_failure(db, tenant_provider_product, watched_api, alert_config):
    """Test creating alert history for endpoint failure."""
    tenant, _, _ = tenant_provider_product

    payload = {
        "type": "endpoint_failure",
        "severity": "critical",
        "subject": "Endpoint Down",
        "details": {
            "endpoint": "GET /v1/users",
            "status_code": 500
        }
    }

    alert_history = AlertHistory(
        tenant_id=tenant.id,
        watched_api_id=watched_api.id,
        alert_config_id=alert_config.id,
        alert_reason="endpoint_down",
        severity="critical",
        endpoint_path="/v1/users",
        http_method="GET",
        payload=payload,
        status="pending"
    )

    db.add(alert_history)
    db.commit()
    db.refresh(alert_history)

    assert alert_history.id is not None
    assert alert_history.alert_reason == "endpoint_down"
    assert alert_history.endpoint_path == "/v1/users"
    assert alert_history.http_method == "GET"
    assert alert_history.version_history_id is None


def test_alert_history_status_transitions(db, tenant_provider_product, watched_api, alert_config):
    """Test alert status transitions: pending -> sent."""
    tenant, _, _ = tenant_provider_product

    alert_history = AlertHistory(
        tenant_id=tenant.id,
        watched_api_id=watched_api.id,
        alert_config_id=alert_config.id,
        alert_reason="breaking_change",
        severity="critical",
        payload={},
        status="pending"
    )

    db.add(alert_history)
    db.commit()
    db.refresh(alert_history)

    assert alert_history.status == "pending"
    assert alert_history.sent_at is None

    # Mark as sent
    sent_time = datetime.now()
    alert_history.status = "sent"
    alert_history.sent_at = sent_time
    db.commit()
    db.refresh(alert_history)

    assert alert_history.status == "sent"
    assert alert_history.sent_at == sent_time


def test_alert_history_status_failed(db, tenant_provider_product, watched_api, alert_config):
    """Test alert status transition to failed with error message."""
    tenant, _, _ = tenant_provider_product

    alert_history = AlertHistory(
        tenant_id=tenant.id,
        watched_api_id=watched_api.id,
        alert_config_id=alert_config.id,
        alert_reason="breaking_change",
        severity="critical",
        payload={},
        status="pending"
    )

    db.add(alert_history)
    db.commit()
    db.refresh(alert_history)

    # Mark as failed
    alert_history.status = "failed"
    alert_history.error_message = "SMTP connection timeout"
    db.commit()
    db.refresh(alert_history)

    assert alert_history.status == "failed"
    assert alert_history.error_message == "SMTP connection timeout"
    assert alert_history.sent_at is None


def test_alert_history_relationships(db, tenant_provider_product, watched_api, alert_config, version_history):
    """Test relationships to tenant, watched_api, alert_config, and version_history."""
    tenant, _, _ = tenant_provider_product

    alert_history = AlertHistory(
        tenant_id=tenant.id,
        watched_api_id=watched_api.id,
        alert_config_id=alert_config.id,
        version_history_id=version_history.id,
        alert_reason="breaking_change",
        severity="critical",
        payload={},
        status="sent"
    )

    db.add(alert_history)
    db.commit()
    db.refresh(alert_history)

    # Test relationships
    assert alert_history.tenant.id == tenant.id
    assert alert_history.tenant.name == tenant.name
    assert alert_history.watched_api.id == watched_api.id
    assert alert_history.watched_api.spec_url == watched_api.spec_url
    assert alert_history.alert_config.id == alert_config.id
    assert alert_history.alert_config.alert_type == "email"
    assert alert_history.version_history.id == version_history.id
    assert alert_history.version_history.version == 1


def test_alert_history_repr(db, tenant_provider_product, watched_api, alert_config):
    """Test the __repr__ method."""
    tenant, _, _ = tenant_provider_product

    alert_history = AlertHistory(
        tenant_id=tenant.id,
        watched_api_id=watched_api.id,
        alert_config_id=alert_config.id,
        alert_reason="endpoint_down",
        severity="critical",
        payload={},
        status="sent"
    )

    db.add(alert_history)
    db.commit()
    db.refresh(alert_history)

    repr_str = repr(alert_history)
    assert "AlertHistory" in repr_str
    assert str(alert_history.id) in repr_str
    assert "endpoint_down" in repr_str
    assert "sent" in repr_str


def test_alert_history_payload_json(db, tenant_provider_product, watched_api, alert_config):
    """Test that payload field correctly stores JSON data."""
    tenant, _, _ = tenant_provider_product

    complex_payload = {
        "type": "breaking_change",
        "severity": "critical",
        "subject": "Breaking Changes Detected",
        "details": {
            "api_url": "https://api.example.com/spec.yaml",
            "version": 5,
            "changes": [
                {"type": "field_removed", "path": "/users/name"},
                {"type": "endpoint_removed", "path": "/v1/legacy"}
            ],
            "summary": "Two breaking changes detected"
        },
        "metadata": {
            "detected_at": "2024-01-15T10:30:00Z",
            "change_count": 2
        }
    }

    alert_history = AlertHistory(
        tenant_id=tenant.id,
        watched_api_id=watched_api.id,
        alert_config_id=alert_config.id,
        alert_reason="breaking_change",
        severity="critical",
        payload=complex_payload,
        status="sent"
    )

    db.add(alert_history)
    db.commit()
    db.refresh(alert_history)

    # Verify JSON is preserved (may be string in SQLite, dict in PostgreSQL)
    import json
    payload = alert_history.payload
    if isinstance(payload, str):
        payload = json.loads(payload)

    # SQLite may return a plain string, PostgreSQL returns dict
    assert payload == complex_payload or json.dumps(payload, sort_keys=True) == json.dumps(complex_payload, sort_keys=True)
    # Check nested structure exists
    if isinstance(payload, dict):
        assert payload["metadata"]["change_count"] == 2
        assert len(payload["details"]["changes"]) == 2


def test_query_alerts_by_status(db, tenant_provider_product, watched_api, alert_config):
    """Test querying alerts by status."""
    tenant, _, _ = tenant_provider_product

    pending_alert = AlertHistory(
        tenant_id=tenant.id,
        watched_api_id=watched_api.id,
        alert_config_id=alert_config.id,
        alert_reason="breaking_change",
        severity="critical",
        payload={},
        status="pending"
    )

    sent_alert = AlertHistory(
        tenant_id=tenant.id,
        watched_api_id=watched_api.id,
        alert_config_id=alert_config.id,
        alert_reason="endpoint_down",
        severity="critical",
        payload={},
        status="sent"
    )

    failed_alert = AlertHistory(
        tenant_id=tenant.id,
        watched_api_id=watched_api.id,
        alert_config_id=alert_config.id,
        alert_reason="breaking_change",
        severity="warning",
        payload={},
        status="failed"
    )

    db.add_all([pending_alert, sent_alert, failed_alert])
    db.commit()

    # Query by status
    pending_alerts = db.query(AlertHistory).filter(
        AlertHistory.watched_api_id == watched_api.id,
        AlertHistory.status == "pending"
    ).all()

    sent_alerts = db.query(AlertHistory).filter(
        AlertHistory.watched_api_id == watched_api.id,
        AlertHistory.status == "sent"
    ).all()

    failed_alerts = db.query(AlertHistory).filter(
        AlertHistory.watched_api_id == watched_api.id,
        AlertHistory.status == "failed"
    ).all()

    assert len(pending_alerts) == 1
    assert len(sent_alerts) == 1
    assert len(failed_alerts) == 1


def test_query_alerts_by_reason(db, tenant_provider_product, watched_api, alert_config):
    """Test querying alerts by reason."""
    tenant, _, _ = tenant_provider_product

    breaking_alert_1 = AlertHistory(
        tenant_id=tenant.id,
        watched_api_id=watched_api.id,
        alert_config_id=alert_config.id,
        alert_reason="breaking_change",
        severity="critical",
        payload={},
        status="sent"
    )

    breaking_alert_2 = AlertHistory(
        tenant_id=tenant.id,
        watched_api_id=watched_api.id,
        alert_config_id=alert_config.id,
        alert_reason="breaking_change",
        severity="critical",
        payload={},
        status="sent"
    )

    endpoint_alert = AlertHistory(
        tenant_id=tenant.id,
        watched_api_id=watched_api.id,
        alert_config_id=alert_config.id,
        alert_reason="endpoint_down",
        severity="critical",
        payload={},
        status="sent"
    )

    db.add_all([breaking_alert_1, breaking_alert_2, endpoint_alert])
    db.commit()

    # Query by reason
    breaking_alerts = db.query(AlertHistory).filter(
        AlertHistory.watched_api_id == watched_api.id,
        AlertHistory.alert_reason == "breaking_change"
    ).all()

    assert len(breaking_alerts) == 2


def test_query_alerts_by_severity(db, tenant_provider_product, watched_api, alert_config):
    """Test querying alerts by severity level."""
    tenant, _, _ = tenant_provider_product

    critical_alert = AlertHistory(
        tenant_id=tenant.id,
        watched_api_id=watched_api.id,
        alert_config_id=alert_config.id,
        alert_reason="breaking_change",
        severity="critical",
        payload={},
        status="sent"
    )

    warning_alert = AlertHistory(
        tenant_id=tenant.id,
        watched_api_id=watched_api.id,
        alert_config_id=alert_config.id,
        alert_reason="non_breaking_change",
        severity="warning",
        payload={},
        status="sent"
    )

    info_alert = AlertHistory(
        tenant_id=tenant.id,
        watched_api_id=watched_api.id,
        alert_config_id=alert_config.id,
        alert_reason="endpoint_recovered",
        severity="info",
        payload={},
        status="sent"
    )

    db.add_all([critical_alert, warning_alert, info_alert])
    db.commit()

    # Query critical alerts
    critical_alerts = db.query(AlertHistory).filter(
        AlertHistory.watched_api_id == watched_api.id,
        AlertHistory.severity == "critical"
    ).all()

    assert len(critical_alerts) == 1
    assert critical_alerts[0].alert_reason == "breaking_change"


def test_multiple_alerts_for_same_version(db, tenant_provider_product, watched_api, version_history):
    """Test that multiple alert configs can create multiple alert history records for same version."""
    tenant, _, _ = tenant_provider_product

    # Create two alert configs
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
        destination="https://hooks.example.com"
    )

    db.add_all([email_config, webhook_config])
    db.commit()

    # Create alert history for each config
    email_alert = AlertHistory(
        tenant_id=tenant.id,
        watched_api_id=watched_api.id,
        alert_config_id=email_config.id,
        version_history_id=version_history.id,
        alert_reason="breaking_change",
        severity="critical",
        payload={},
        status="sent"
    )

    webhook_alert = AlertHistory(
        tenant_id=tenant.id,
        watched_api_id=watched_api.id,
        alert_config_id=webhook_config.id,
        version_history_id=version_history.id,
        alert_reason="breaking_change",
        severity="critical",
        payload={},
        status="sent"
    )

    db.add_all([email_alert, webhook_alert])
    db.commit()

    # Query alerts for this version
    version_alerts = db.query(AlertHistory).filter(
        AlertHistory.version_history_id == version_history.id
    ).all()

    assert len(version_alerts) == 2
    alert_config_ids = {alert.alert_config_id for alert in version_alerts}
    assert email_config.id in alert_config_ids
    assert webhook_config.id in alert_config_ids
