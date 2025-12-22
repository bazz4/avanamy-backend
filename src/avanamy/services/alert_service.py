"""
Alert service for sending notifications about API changes and health issues.

Supports multiple alert types:
- Email
- Webhook (HTTP POST)
- Slack (future)
"""

import logging
import smtplib
import httpx
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional, Dict, Any
from datetime import datetime
from uuid import UUID

from sqlalchemy.orm import Session
from opentelemetry import trace
from prometheus_client import Counter

from avanamy.models.alert_configuration import AlertConfiguration
from avanamy.models.alert_history import AlertHistory
from avanamy.models.watched_api import WatchedAPI
from avanamy.models.version_history import VersionHistory

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)

# Prometheus metrics
alerts_sent_total = Counter(
    'alerts_sent_total',
    'Total number of alerts sent',
    ['alert_type', 'reason', 'severity']
)

alerts_failed_total = Counter(
    'alerts_failed_total',
    'Total number of failed alert attempts',
    ['alert_type', 'reason']
)


class AlertService:
    """Service for sending alerts via various channels."""

    def __init__(self, db: Session):
        self.db = db

    async def send_breaking_change_alert(
        self,
        watched_api: WatchedAPI,
        version_history: VersionHistory,
        diff: Dict[str, Any],
        summary: Optional[str] = None
    ):
        """
        Send alerts for breaking API changes.
        
        Args:
            watched_api: The WatchedAPI that changed
            version_history: The new version with breaking changes
            diff: The diff object containing change details
            summary: AI-generated summary of changes
        """
        with tracer.start_as_current_span("alert.send_breaking_change") as span:
            span.set_attribute("watched_api.id", str(watched_api.id))
            span.set_attribute("version", version_history.version)
            
            logger.info(
                "Sending breaking change alerts: watched_api=%s version=%s",
                watched_api.id, version_history.version
            )

            # Get alert configurations for this watched API
            configs = self.db.query(AlertConfiguration).filter(
                AlertConfiguration.watched_api_id == watched_api.id,
                AlertConfiguration.enabled == True,
                AlertConfiguration.alert_on_breaking_changes == True
            ).all()

            if not configs:
                logger.info("No alert configurations found for breaking changes")
                return

            # Prepare alert payload
            payload = self._build_breaking_change_payload(
                watched_api, version_history, diff, summary
            )

            # Send to each configured destination
            for config in configs:
                await self._send_alert(
                    config=config,
                    alert_reason="breaking_change",
                    severity="critical",
                    payload=payload,
                    version_history_id=version_history.id
                )

    async def send_endpoint_failure_alert(
        self,
        watched_api: WatchedAPI,
        endpoint_path: str,
        http_method: str,
        status_code: int,
        error_message: Optional[str] = None
    ):
        """
        Send alerts when an endpoint starts failing.
        
        Args:
            watched_api: The WatchedAPI with failing endpoint
            endpoint_path: The endpoint path (e.g., /v1/users)
            http_method: HTTP method (GET, POST, etc.)
            status_code: The error status code (500, 503, etc.)
            error_message: Optional error details
        """
        with tracer.start_as_current_span("alert.send_endpoint_failure") as span:
            span.set_attribute("watched_api.id", str(watched_api.id))
            span.set_attribute("endpoint.path", endpoint_path)
            span.set_attribute("endpoint.method", http_method)
            span.set_attribute("status_code", status_code)
            
            logger.warning(
                "Sending endpoint failure alerts: %s %s returned %s",
                http_method, endpoint_path, status_code
            )

            # Get alert configurations
            configs = self.db.query(AlertConfiguration).filter(
                AlertConfiguration.watched_api_id == watched_api.id,
                AlertConfiguration.enabled == True,
                AlertConfiguration.alert_on_endpoint_failures == True
            ).all()

            if not configs:
                return

            # Prepare payload
            payload = self._build_endpoint_failure_payload(
                watched_api, endpoint_path, http_method, status_code, error_message
            )

            # Send alerts
            for config in configs:
                await self._send_alert(
                    config=config,
                    alert_reason="endpoint_down",
                    severity="critical",
                    payload=payload,
                    endpoint_path=endpoint_path,
                    http_method=http_method
                )

    async def _send_alert(
        self,
        config: AlertConfiguration,
        alert_reason: str,
        severity: str,
        payload: Dict[str, Any],
        version_history_id: Optional[int] = None,
        endpoint_path: Optional[str] = None,
        http_method: Optional[str] = None
    ):
        """
        Send a single alert and record it in alert_history.
        
        Args:
            config: AlertConfiguration with destination details
            alert_reason: Reason for alert (breaking_change, endpoint_down, etc.)
            severity: Severity level (info, warning, critical)
            payload: The alert content
            version_history_id: Optional link to version
            endpoint_path: Optional endpoint path
            http_method: Optional HTTP method
        """
        with tracer.start_as_current_span("alert.send_individual") as span:
            span.set_attribute("alert.type", config.alert_type)
            span.set_attribute("alert.reason", alert_reason)
            span.set_attribute("alert.severity", severity)

            # Create alert history record
            alert_history = AlertHistory(
                tenant_id=config.tenant_id,
                watched_api_id=config.watched_api_id,
                alert_config_id=config.id,
                version_history_id=version_history_id,
                alert_reason=alert_reason,
                severity=severity,
                endpoint_path=endpoint_path,
                http_method=http_method,
                payload=payload,
                status="pending"
            )
            self.db.add(alert_history)
            self.db.flush()  # Get ID

            try:
                # Send via appropriate channel
                if config.alert_type == "email":
                    await self._send_email_alert(config.destination, payload)
                elif config.alert_type == "webhook":
                    await self._send_webhook_alert(config.destination, payload)
                elif config.alert_type == "slack":
                    await self._send_slack_alert(config.destination, payload)
                else:
                    raise ValueError(f"Unknown alert type: {config.alert_type}")

                # Mark as sent
                alert_history.status = "sent"
                alert_history.sent_at = datetime.now()
                self.db.commit()

                # Update metrics
                alerts_sent_total.labels(
                    alert_type=config.alert_type,
                    reason=alert_reason,
                    severity=severity
                ).inc()

                logger.info(
                    "Alert sent successfully: id=%s type=%s destination=%s",
                    alert_history.id, config.alert_type, config.destination
                )

            except Exception as e:
                # Mark as failed
                alert_history.status = "failed"
                alert_history.error_message = str(e)
                self.db.commit()

                # Update metrics
                alerts_failed_total.labels(
                    alert_type=config.alert_type,
                    reason=alert_reason
                ).inc()

                logger.error(
                    "Failed to send alert: id=%s type=%s error=%s",
                    alert_history.id, config.alert_type, str(e)
                )
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))

    async def _send_email_alert(self, email: str, payload: Dict[str, Any]):
        """Send alert via email."""
        # TODO: Implement with proper SMTP configuration
        # For now, just log
        logger.info(f"Would send email to {email}: {payload.get('subject')}")
        
        # In production, use something like:
        # msg = MIMEMultipart()
        # msg['From'] = "alerts@avanamy.com"
        # msg['To'] = email
        # msg['Subject'] = payload['subject']
        # msg.attach(MIMEText(payload['body'], 'html'))
        # 
        # with smtplib.SMTP(smtp_host, smtp_port) as server:
        #     server.send_message(msg)

    async def _send_webhook_alert(self, webhook_url: str, payload: Dict[str, Any]):
        """Send alert via webhook (HTTP POST)."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                webhook_url,
                json=payload,
                headers={"Content-Type": "application/json"}
            )
            response.raise_for_status()
            
        logger.info(f"Webhook alert sent to {webhook_url}: status {response.status_code}")

    async def _send_slack_alert(self, channel: str, payload: Dict[str, Any]):
        """Send alert to Slack channel."""
        # TODO: Implement Slack webhook integration
        logger.info(f"Would send Slack alert to {channel}: {payload.get('text')}")

    def _build_breaking_change_payload(
        self,
        watched_api: WatchedAPI,
        version_history: VersionHistory,
        diff: Dict[str, Any],
        summary: Optional[str]
    ) -> Dict[str, Any]:
        """Build payload for breaking change alert."""
        changes = diff.get('changes', [])
        change_count = len(changes)
        
        return {
            "type": "breaking_change",
            "severity": "critical",
            "subject": f"⚠️ Breaking Change Detected: {watched_api.spec_url}",
            "text": f"Breaking changes detected in version {version_history.version}",
            "details": {
                "api_url": watched_api.spec_url,
                "version": version_history.version,
                "change_count": change_count,
                "changes": changes[:10],  # Limit to first 10
                "summary": summary,
                "timestamp": datetime.now().isoformat()
            },
            "body": self._format_breaking_change_html(
                watched_api, version_history, changes, summary
            )
        }

    def _build_endpoint_failure_payload(
        self,
        watched_api: WatchedAPI,
        endpoint_path: str,
        http_method: str,
        status_code: int,
        error_message: Optional[str]
    ) -> Dict[str, Any]:
        """Build payload for endpoint failure alert."""
        return {
            "type": "endpoint_failure",
            "severity": "critical",
            "subject": f"🔴 Endpoint Down: {http_method} {endpoint_path}",
            "text": f"Endpoint {http_method} {endpoint_path} is returning {status_code}",
            "details": {
                "api_url": watched_api.spec_url,
                "endpoint": f"{http_method} {endpoint_path}",
                "status_code": status_code,
                "error_message": error_message,
                "timestamp": datetime.now().isoformat()
            },
            "body": self._format_endpoint_failure_html(
                watched_api, endpoint_path, http_method, status_code, error_message
            )
        }

    def _format_breaking_change_html(
        self,
        watched_api: WatchedAPI,
        version_history: VersionHistory,
        changes: list,
        summary: Optional[str]
    ) -> str:
        """Format breaking change alert as HTML."""
        changes_html = "<ul>"
        for change in changes[:10]:
            changes_html += f"<li>{change.get('type', 'Unknown')}: {change.get('path', '')}</li>"
        changes_html += "</ul>"
        
        return f"""
        <html>
        <body>
            <h2>⚠️ Breaking Change Detected</h2>
            <p><strong>API:</strong> {watched_api.spec_url}</p>
            <p><strong>Version:</strong> {version_history.version}</p>
            <p><strong>Changes:</strong> {len(changes)} breaking changes detected</p>
            
            {f'<h3>Summary</h3><p>{summary}</p>' if summary else ''}
            
            <h3>Changes</h3>
            {changes_html}
            
            <p><small>Detected at {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}</small></p>
        </body>
        </html>
        """

    def _format_endpoint_failure_html(
        self,
        watched_api: WatchedAPI,
        endpoint_path: str,
        http_method: str,
        status_code: int,
        error_message: Optional[str]
    ) -> str:
        """Format endpoint failure alert as HTML."""
        return f"""
        <html>
        <body>
            <h2>🔴 Endpoint Failure Alert</h2>
            <p><strong>API:</strong> {watched_api.spec_url}</p>
            <p><strong>Endpoint:</strong> {http_method} {endpoint_path}</p>
            <p><strong>Status Code:</strong> {status_code}</p>
            
            {f'<p><strong>Error:</strong> {error_message}</p>' if error_message else ''}
            
            <p>This endpoint is currently returning errors and may be unavailable.</p>
            
            <p><small>Detected at {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}</small></p>
        </body>
        </html>
        """