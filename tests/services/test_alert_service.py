"""
Unit tests for AlertService.

Tests sending alerts via different channels (email, webhook, slack),
handling success and failure cases, recording alert history, and updating metrics.
"""
import pytest
import uuid
from unittest.mock import MagicMock, AsyncMock, patch, call
import httpx
from datetime import datetime

from avanamy.services.alert_service import AlertService
from avanamy.models.alert_configuration import AlertConfiguration
from avanamy.models.alert_history import AlertHistory
from avanamy.models.watched_api import WatchedAPI
from avanamy.models.version_history import VersionHistory
from avanamy.models.api_spec import ApiSpec
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
        spec_url="https://api.stripe.com/openapi.yaml",
        polling_enabled=True,
        status="active"
    )
    db.add(api)
    db.commit()
    db.refresh(api)
    return api


@pytest.fixture
def version_history(db, tenant_provider_product):
    """Create a test VersionHistory record."""
    tenant, provider, product = tenant_provider_product

    # Create ApiSpec first
    spec = ApiSpec(
        tenant_id=tenant.id,
        api_product_id=product.id,
        provider_id=provider.id,
        name="Stripe API",
        version="v2",
        description="Stripe OpenAPI spec",
        original_file_s3_path="s3://test-bucket/stripe-spec.yaml"
    )
    db.add(spec)
    db.commit()
    db.refresh(spec)

    # Create VersionHistory
    version = VersionHistory(
        api_spec_id=spec.id,
        version=2
    )
    db.add(version)
    db.commit()
    db.refresh(version)
    return version


@pytest.fixture
def email_alert_config(db, tenant_provider_product, watched_api):
    """Create an email alert configuration."""
    tenant, _, _ = tenant_provider_product
    config = AlertConfiguration(
        tenant_id=tenant.id,
        watched_api_id=watched_api.id,
        alert_type="email",
        destination="team@example.com",
        alert_on_breaking_changes=True,
        alert_on_endpoint_failures=True,
        enabled=True
    )
    db.add(config)
    db.commit()
    db.refresh(config)
    return config


@pytest.fixture
def webhook_alert_config(db, tenant_provider_product, watched_api):
    """Create a webhook alert configuration."""
    tenant, _, _ = tenant_provider_product
    config = AlertConfiguration(
        tenant_id=tenant.id,
        watched_api_id=watched_api.id,
        alert_type="webhook",
        destination="https://hooks.example.com/alerts",
        alert_on_breaking_changes=True,
        alert_on_endpoint_failures=True,
        enabled=True
    )
    db.add(config)
    db.commit()
    db.refresh(config)
    return config


@pytest.fixture
def disabled_alert_config(db, tenant_provider_product, watched_api):
    """Create a disabled alert configuration."""
    tenant, _, _ = tenant_provider_product
    config = AlertConfiguration(
        tenant_id=tenant.id,
        watched_api_id=watched_api.id,
        alert_type="email",
        destination="disabled@example.com",
        alert_on_breaking_changes=True,
        enabled=False
    )
    db.add(config)
    db.commit()
    db.refresh(config)
    return config


class TestSendBreakingChangeAlert:
    """Tests for send_breaking_change_alert method."""

    async def test_send_breaking_change_alert_success(
        self, db, watched_api, version_history, email_alert_config
    ):
        """Test sending breaking change alert successfully."""
        service = AlertService(db)

        diff = {
            "changes": [
                {"type": "field_removed", "path": "/users/email"},
                {"type": "endpoint_removed", "path": "/v1/legacy"}
            ]
        }
        summary = "Two breaking changes detected"

        with patch.object(service, "_send_email_alert", new_callable=AsyncMock) as mock_email:
            await service.send_breaking_change_alert(
                watched_api, version_history, diff, summary
            )

            # Verify email was called
            mock_email.assert_called_once()
            call_args = mock_email.call_args
            assert call_args[0][0] == "team@example.com"
            payload = call_args[0][1]
            assert payload["type"] == "breaking_change"
            assert payload["severity"] == "critical"
            assert "Breaking Change" in payload["subject"]
            assert payload["details"]["version"] == 2
            assert payload["details"]["change_count"] == 2

        # Verify alert history was created
        history = db.query(AlertHistory).filter(
            AlertHistory.watched_api_id == watched_api.id,
            AlertHistory.alert_reason == "breaking_change"
        ).first()

        assert history is not None
        assert history.status == "sent"
        assert history.severity == "critical"
        assert history.version_history_id == version_history.id
        assert history.sent_at is not None

    async def test_send_breaking_change_alert_no_configs(
        self, db, watched_api, version_history
    ):
        """Test sending alert when no alert configurations exist."""
        service = AlertService(db)

        diff = {"changes": [{"type": "field_removed", "path": "/users/name"}]}

        with patch.object(service, "_send_email_alert", new_callable=AsyncMock) as mock_email:
            await service.send_breaking_change_alert(
                watched_api, version_history, diff, None
            )

            # No alerts should be sent
            mock_email.assert_not_called()

        # No alert history should be created
        history = db.query(AlertHistory).filter(
            AlertHistory.watched_api_id == watched_api.id
        ).all()
        assert len(history) == 0

    async def test_send_breaking_change_alert_disabled_config(
        self, db, watched_api, version_history, disabled_alert_config
    ):
        """Test that disabled alert configs are not triggered."""
        service = AlertService(db)

        diff = {"changes": [{"type": "field_removed", "path": "/users/name"}]}

        with patch.object(service, "_send_email_alert", new_callable=AsyncMock) as mock_email:
            await service.send_breaking_change_alert(
                watched_api, version_history, diff, None
            )

            # No alerts should be sent (config is disabled)
            mock_email.assert_not_called()

    async def test_send_breaking_change_alert_multiple_configs(
        self, db, watched_api, version_history, email_alert_config, webhook_alert_config
    ):
        """Test sending alerts to multiple configured destinations."""
        service = AlertService(db)

        diff = {"changes": [{"type": "endpoint_removed", "path": "/v1/old"}]}

        with patch.object(service, "_send_email_alert", new_callable=AsyncMock) as mock_email:
            with patch.object(service, "_send_webhook_alert", new_callable=AsyncMock) as mock_webhook:
                await service.send_breaking_change_alert(
                    watched_api, version_history, diff, None
                )

                # Both alerts should be sent
                mock_email.assert_called_once()
                mock_webhook.assert_called_once()

        # Two alert history records should be created
        history = db.query(AlertHistory).filter(
            AlertHistory.watched_api_id == watched_api.id
        ).all()
        assert len(history) == 2
        assert all(h.status == "sent" for h in history)

    async def test_send_breaking_change_alert_failure(
        self, db, watched_api, version_history, email_alert_config
    ):
        """Test handling alert sending failure."""
        service = AlertService(db)

        diff = {"changes": [{"type": "field_removed", "path": "/users/name"}]}

        # Simulate email sending failure
        with patch.object(
            service, "_send_email_alert",
            new_callable=AsyncMock,
            side_effect=Exception("SMTP connection failed")
        ):
            await service.send_breaking_change_alert(
                watched_api, version_history, diff, None
            )

        # Alert history should be created with failed status
        history = db.query(AlertHistory).filter(
            AlertHistory.watched_api_id == watched_api.id
        ).first()

        assert history is not None
        assert history.status == "failed"
        assert history.error_message == "SMTP connection failed"
        assert history.sent_at is None


class TestSendEndpointFailureAlert:
    """Tests for send_endpoint_failure_alert method."""

    async def test_send_endpoint_failure_alert_success(
        self, db, watched_api, email_alert_config
    ):
        """Test sending endpoint failure alert successfully."""
        service = AlertService(db)

        with patch.object(service, "_send_email_alert", new_callable=AsyncMock) as mock_email:
            await service.send_endpoint_failure_alert(
                watched_api=watched_api,
                endpoint_path="/v1/users",
                http_method="GET",
                status_code=500,
                error_message="Database connection timeout"
            )

            # Verify email was called
            mock_email.assert_called_once()
            call_args = mock_email.call_args
            payload = call_args[0][1]
            assert payload["type"] == "endpoint_failure"
            assert payload["severity"] == "critical"
            assert "Endpoint Down" in payload["subject"]
            assert payload["details"]["endpoint"] == "GET /v1/users"
            assert payload["details"]["status_code"] == 500

        # Verify alert history was created
        history = db.query(AlertHistory).filter(
            AlertHistory.watched_api_id == watched_api.id,
            AlertHistory.alert_reason == "endpoint_down"
        ).first()

        assert history is not None
        assert history.status == "sent"
        assert history.severity == "critical"
        assert history.endpoint_path == "/v1/users"
        assert history.http_method == "GET"
        assert history.version_history_id is None

    async def test_send_endpoint_failure_alert_no_configs(
        self, db, watched_api
    ):
        """Test endpoint failure alert with no configurations."""
        service = AlertService(db)

        with patch.object(service, "_send_email_alert", new_callable=AsyncMock) as mock_email:
            await service.send_endpoint_failure_alert(
                watched_api=watched_api,
                endpoint_path="/v1/test",
                http_method="POST",
                status_code=503,
                error_message=None
            )

            # No alerts should be sent
            mock_email.assert_not_called()


class TestSendWebhookAlert:
    """Tests for _send_webhook_alert method."""

    async def test_send_webhook_alert_success(self):
        """Test sending webhook alert with HTTP 200 response."""
        db = MagicMock()
        service = AlertService(db)

        payload = {
            "type": "breaking_change",
            "severity": "critical",
            "details": {"version": 2}
        }

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_response = AsyncMock()
            mock_response.status_code = 200
            mock_response.raise_for_status = MagicMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value.__aenter__.return_value = mock_client

            await service._send_webhook_alert(
                "https://hooks.example.com/alerts",
                payload
            )

            # Verify HTTP POST was called correctly
            mock_client.post.assert_called_once()
            call_args = mock_client.post.call_args
            assert call_args[0][0] == "https://hooks.example.com/alerts"
            assert call_args[1]["json"] == payload
            assert call_args[1]["headers"]["Content-Type"] == "application/json"

    async def test_send_webhook_alert_http_error(self):
        """Test handling HTTP error when sending webhook."""
        db = MagicMock()
        service = AlertService(db)

        payload = {"type": "test"}

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_response = AsyncMock()
            mock_response.status_code = 500
            mock_response.raise_for_status = MagicMock(
                side_effect=httpx.HTTPStatusError(
                    "500 Server Error",
                    request=MagicMock(),
                    response=mock_response
                )
            )
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value.__aenter__.return_value = mock_client

            with pytest.raises(httpx.HTTPStatusError):
                await service._send_webhook_alert(
                    "https://hooks.example.com/alerts",
                    payload
                )

    async def test_send_webhook_alert_timeout(self):
        """Test handling timeout when sending webhook."""
        db = MagicMock()
        service = AlertService(db)

        payload = {"type": "test"}

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(
                side_effect=httpx.TimeoutException("Request timeout")
            )
            mock_client_class.return_value.__aenter__.return_value = mock_client

            with pytest.raises(httpx.TimeoutException):
                await service._send_webhook_alert(
                    "https://hooks.example.com/alerts",
                    payload
                )

    async def test_send_webhook_alert_network_error(self):
        """Test handling network error when sending webhook."""
        db = MagicMock()
        service = AlertService(db)

        payload = {"type": "test"}

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(
                side_effect=httpx.ConnectError("Connection refused")
            )
            mock_client_class.return_value.__aenter__.return_value = mock_client

            with pytest.raises(httpx.ConnectError):
                await service._send_webhook_alert(
                    "https://hooks.example.com/alerts",
                    payload
                )


class TestSendEmailAlert:
    """Tests for _send_email_alert method."""

    async def test_send_email_alert_logs_correctly(self):
        """Test that email sending is logged (actual SMTP not configured in tests)."""
        db = MagicMock()
        service = AlertService(db)

        payload = {
            "subject": "Breaking Change Detected",
            "body": "<html>Alert content</html>"
        }

        # Currently just logs, doesn't send actual email
        with patch("avanamy.services.alert_service.logger") as mock_logger:
            await service._send_email_alert("test@example.com", payload)

            # Verify logging occurred
            mock_logger.info.assert_called_once()
            log_call = mock_logger.info.call_args[0][0]
            assert "test@example.com" in log_call
            assert "Breaking Change Detected" in log_call


class TestSendSlackAlert:
    """Tests for _send_slack_alert method."""

    async def test_send_slack_alert_logs_correctly(self):
        """Test that Slack sending is logged (not yet implemented)."""
        db = MagicMock()
        service = AlertService(db)

        payload = {
            "text": "Breaking change detected in API"
        }

        # Currently just logs, doesn't send actual Slack message
        with patch("avanamy.services.alert_service.logger") as mock_logger:
            await service._send_slack_alert("#api-alerts", payload)

            # Verify logging occurred
            mock_logger.info.assert_called_once()
            log_call = mock_logger.info.call_args[0][0]
            assert "#api-alerts" in log_call


class TestAlertHistoryRecording:
    """Tests for alert history recording."""

    async def test_alert_history_updated_to_sent(
        self, db, watched_api, email_alert_config, version_history
    ):
        """Test that alert history status is updated to 'sent' on success."""
        service = AlertService(db)

        diff = {"changes": [{"type": "field_removed", "path": "/users/name"}]}

        with patch.object(service, "_send_email_alert", new_callable=AsyncMock):
            await service.send_breaking_change_alert(
                watched_api, version_history, diff, None
            )

        history = db.query(AlertHistory).filter(
            AlertHistory.watched_api_id == watched_api.id
        ).first()

        assert history.status == "sent"
        assert history.sent_at is not None
        assert history.error_message is None

    async def test_alert_history_updated_to_failed(
        self, db, watched_api, email_alert_config, version_history
    ):
        """Test that alert history status is updated to 'failed' on error."""
        service = AlertService(db)

        diff = {"changes": [{"type": "field_removed", "path": "/users/name"}]}

        with patch.object(
            service, "_send_email_alert",
            new_callable=AsyncMock,
            side_effect=Exception("Network error")
        ):
            await service.send_breaking_change_alert(
                watched_api, version_history, diff, None
            )

        history = db.query(AlertHistory).filter(
            AlertHistory.watched_api_id == watched_api.id
        ).first()

        assert history.status == "failed"
        assert history.error_message == "Network error"
        assert history.sent_at is None


class TestPrometheusMetrics:
    """Tests for Prometheus metrics tracking."""

    async def test_alerts_sent_metric_incremented(
        self, db, watched_api, email_alert_config, version_history
    ):
        """Test that alerts_sent_total metric is incremented on success."""
        service = AlertService(db)

        diff = {"changes": [{"type": "field_removed", "path": "/users/name"}]}

        with patch("avanamy.services.alert_service.alerts_sent_total") as mock_metric:
            with patch.object(service, "_send_email_alert", new_callable=AsyncMock):
                await service.send_breaking_change_alert(
                    watched_api, version_history, diff, None
                )

                # Verify metric was incremented
                mock_metric.labels.assert_called_once_with(
                    alert_type="email",
                    reason="breaking_change",
                    severity="critical"
                )
                mock_metric.labels.return_value.inc.assert_called_once()

    async def test_alerts_failed_metric_incremented(
        self, db, watched_api, email_alert_config, version_history
    ):
        """Test that alerts_failed_total metric is incremented on failure."""
        service = AlertService(db)

        diff = {"changes": [{"type": "field_removed", "path": "/users/name"}]}

        with patch("avanamy.services.alert_service.alerts_failed_total") as mock_metric:
            with patch.object(
                service, "_send_email_alert",
                new_callable=AsyncMock,
                side_effect=Exception("Failed")
            ):
                await service.send_breaking_change_alert(
                    watched_api, version_history, diff, None
                )

                # Verify metric was incremented
                mock_metric.labels.assert_called_once_with(
                    alert_type="email",
                    reason="breaking_change"
                )
                mock_metric.labels.return_value.inc.assert_called_once()


class TestPayloadBuilding:
    """Tests for payload building methods."""

    def test_build_breaking_change_payload(self, db, watched_api, version_history):
        """Test building payload for breaking change alert."""
        service = AlertService(db)

        diff = {
            "changes": [
                {"type": "field_removed", "path": "/users/email"},
                {"type": "endpoint_removed", "path": "/v1/old"}
            ]
        }
        summary = "Two critical changes detected"

        payload = service._build_breaking_change_payload(
            watched_api, version_history, diff, summary
        )

        assert payload["type"] == "breaking_change"
        assert payload["severity"] == "critical"
        assert "Breaking Change" in payload["subject"]
        assert watched_api.spec_url in payload["subject"]
        assert payload["details"]["api_url"] == watched_api.spec_url
        assert payload["details"]["version"] == 2
        assert payload["details"]["change_count"] == 2
        assert payload["details"]["summary"] == summary
        assert len(payload["details"]["changes"]) == 2

    def test_build_breaking_change_payload_limits_changes(
        self, db, watched_api, version_history
    ):
        """Test that payload limits changes to first 10."""
        service = AlertService(db)

        # Create 15 changes
        changes = [{"type": f"change_{i}", "path": f"/path/{i}"} for i in range(15)]
        diff = {"changes": changes}

        payload = service._build_breaking_change_payload(
            watched_api, version_history, diff, None
        )

        # Should only include first 10
        assert payload["details"]["change_count"] == 15
        assert len(payload["details"]["changes"]) == 10

    def test_build_endpoint_failure_payload(self, db, watched_api):
        """Test building payload for endpoint failure alert."""
        service = AlertService(db)

        payload = service._build_endpoint_failure_payload(
            watched_api=watched_api,
            endpoint_path="/v1/payments",
            http_method="POST",
            status_code=503,
            error_message="Service temporarily unavailable"
        )

        assert payload["type"] == "endpoint_failure"
        assert payload["severity"] == "critical"
        assert "Endpoint Down" in payload["subject"]
        assert "POST /v1/payments" in payload["subject"]
        assert payload["details"]["api_url"] == watched_api.spec_url
        assert payload["details"]["endpoint"] == "POST /v1/payments"
        assert payload["details"]["status_code"] == 503
        assert payload["details"]["error_message"] == "Service temporarily unavailable"


class TestUnknownAlertType:
    """Tests for handling unknown alert types."""

    async def test_unknown_alert_type_raises_error(
        self, db, tenant_provider_product, watched_api, version_history
    ):
        """Test that unknown alert type raises ValueError."""
        tenant, _, _ = tenant_provider_product

        # Create alert config with invalid type
        invalid_config = AlertConfiguration(
            tenant_id=tenant.id,
            watched_api_id=watched_api.id,
            alert_type="invalid_type",
            destination="test@example.com",
            alert_on_breaking_changes=True,
            enabled=True
        )
        db.add(invalid_config)
        db.commit()

        service = AlertService(db)
        diff = {"changes": [{"type": "test"}]}

        await service.send_breaking_change_alert(
            watched_api, version_history, diff, None
        )

        # Check that alert failed with appropriate error
        history = db.query(AlertHistory).filter(
            AlertHistory.watched_api_id == watched_api.id
        ).first()

        assert history.status == "failed"
        assert "Unknown alert type" in history.error_message
