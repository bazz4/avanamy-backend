"""
Email service for sending alert notifications.

Simple SMTP-based email sending. Can be upgraded to queue-based
system later without changing the calling code.
"""

import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional, Dict, Any
from datetime import datetime
import os

from sqlalchemy.orm import Session
from avanamy.models.alert_history import AlertHistory

logger = logging.getLogger(__name__)


class EmailService:
    """
    Simple email service using SMTP.
    
    Configuration via environment variables:
    - SMTP_HOST: SMTP server (default: localhost)
    - SMTP_PORT: SMTP port (default: 587)
    - SMTP_USERNAME: SMTP username
    - SMTP_PASSWORD: SMTP password
    - SMTP_USE_TLS: Use TLS (default: true)
    - SMTP_FROM_EMAIL: From email address (default: alerts@avanamy.com)
    - SMTP_FROM_NAME: From name (default: Avanamy Alerts)
    """
    
    def __init__(self):
        """Initialize email service with SMTP configuration from env."""
        self.smtp_host = os.getenv("SMTP_HOST", "localhost")
        self.smtp_port = int(os.getenv("SMTP_PORT", "587"))
        self.smtp_username = os.getenv("SMTP_USERNAME")
        self.smtp_password = os.getenv("SMTP_PASSWORD")
        self.smtp_use_tls = os.getenv("SMTP_USE_TLS", "true").lower() == "true"
        self.from_email = os.getenv("SMTP_FROM_EMAIL", "alerts@avanamy.com")
        self.from_name = os.getenv("SMTP_FROM_NAME", "Avanamy Alerts")
    
    def send_breaking_change_alert(
        self,
        db: Session,
        alert_config: Any,  # AlertConfiguration
        watched_api: Any,   # WatchedAPI
        version: Any,       # VersionHistory
        breaking_changes_count: int
    ) -> bool:
        """
        Send alert for breaking changes detected.
        
        Args:
            db: Database session
            alert_config: Alert configuration with destination
            watched_api: The watched API that changed
            version: The new version with changes
            breaking_changes_count: Number of breaking changes
            
        Returns:
            True if sent successfully
        """
        subject = f"🚨 Breaking Change Detected - {watched_api.api_spec.name}"
        
        body = f"""
        <h2>Breaking Change Alert</h2>
        
        <p><strong>API:</strong> {watched_api.api_spec.name}</p>
        <p><strong>Version:</strong> {version.version}</p>
        <p><strong>Breaking Changes:</strong> {breaking_changes_count}</p>
        <p><strong>Time:</strong> {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}</p>
        
        <h3>Summary</h3>
        <p>{version.summary or 'Breaking changes detected in API specification.'}</p>
        
        <p><a href="http://localhost:3000/specs/{watched_api.api_spec_id}/versions/{version.version}/diff">
            View Full Details →
        </a></p>
        """
        
        success = self._send_email(
            to=alert_config.destination,
            subject=subject,
            html_body=body
        )
        
        # Record in alert history
        self._record_history(
            db=db,
            alert_config=alert_config,
            watched_api=watched_api,
            version_history_id=version.id,
            alert_reason="breaking_change",
            severity="critical",
            payload={
                "api_name": watched_api.api_spec.name,
                "version": version.version,
                "breaking_changes_count": breaking_changes_count,
                "summary": version.summary
            },
            status="sent" if success else "failed",
            error_message=None if success else "Failed to send email"
        )
        
        return success
    
    def send_non_breaking_change_alert(
        self,
        db: Session,
        alert_config: Any,
        watched_api: Any,
        version: Any
    ) -> bool:
        """Send alert for non-breaking changes."""
        subject = f"ℹ️ API Change Detected - {watched_api.api_spec.name}"
        
        body = f"""
        <h2>API Change Alert</h2>
        
        <p><strong>API:</strong> {watched_api.api_spec.name}</p>
        <p><strong>Version:</strong> {version.version}</p>
        <p><strong>Type:</strong> Non-breaking changes</p>
        <p><strong>Time:</strong> {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}</p>
        
        <h3>Summary</h3>
        <p>{version.summary or 'Non-breaking changes detected in API specification.'}</p>
        
        <p><a href="http://localhost:3000/specs/{watched_api.api_spec_id}/versions/{version.version}/diff">
            View Full Details →
        </a></p>
        """
        
        success = self._send_email(
            to=alert_config.destination,
            subject=subject,
            html_body=body
        )
        
        self._record_history(
            db=db,
            alert_config=alert_config,
            watched_api=watched_api,
            version_history_id=version.id,
            alert_reason="non_breaking_change",
            severity="info",
            payload={
                "api_name": watched_api.api_spec.name,
                "version": version.version,
                "summary": version.summary
            },
            status="sent" if success else "failed",
            error_message=None if success else "Failed to send email"
        )
        
        return success
    
    def send_endpoint_down_alert(
        self,
        db: Session,
        alert_config: Any,
        watched_api: Any,
        endpoint_path: str,
        http_method: str,
        status_code: int,
        error_message: Optional[str]
    ) -> bool:
        """Send alert when endpoint goes down."""
        api_name = watched_api.api_spec.name if watched_api.api_spec else watched_api.spec_url
        
        subject = f"🚨 Poll Failed - {api_name}"
        
        body = f"""
        <h2>Polling Failure Alert</h2>
        
        <p><strong>API:</strong> {api_name}</p>
        <p><strong>URL:</strong> {endpoint_path}</p>
        <p><strong>Status Code:</strong> {status_code}</p>
        <p><strong>Time:</strong> {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}</p>
        
        <h3>Error</h3>
        <p>{error_message or 'Failed to fetch API spec.'}</p>
        
        <p><a href="http://localhost:3000/watched-apis/{watched_api.id}">
            View API Dashboard →
        </a></p>
        """
        
        success = self._send_email(
            to=alert_config.destination,
            subject=subject,
            html_body=body
        )
        
        self._record_history(
            db=db,
            alert_config=alert_config,
            watched_api=watched_api,
            version_history_id=None,
            alert_reason="endpoint_down",
            severity="critical",
            endpoint_path=endpoint_path,
            http_method=http_method,
            payload={
                "endpoint_path": endpoint_path,
                "http_method": http_method,
                "status_code": status_code,
                "error_message": error_message
            },
            status="sent" if success else "failed",
            error_message=None if success else "Failed to send email"
        )
        
        return success
    
    def send_endpoint_recovered_alert(
        self,
        db: Session,
        alert_config: Any,
        watched_api: Any,
        endpoint_path: str,
        http_method: str
    ) -> bool:
        """Send alert when endpoint recovers."""
        subject = f"✅ Endpoint Recovered - {http_method} {endpoint_path}"
        
        body = f"""
        <h2>Endpoint Recovery</h2>
        
        <p><strong>API:</strong> {watched_api.api_spec.name}</p>
        <p><strong>Endpoint:</strong> {http_method} {endpoint_path}</p>
        <p><strong>Status:</strong> Healthy</p>
        <p><strong>Time:</strong> {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}</p>
        
        <p>The endpoint is now responding normally.</p>
        
        <p><a href="http://localhost:3000/watched-apis/{watched_api.id}">
            View API Dashboard →
        </a></p>
        """
        
        success = self._send_email(
            to=alert_config.destination,
            subject=subject,
            html_body=body
        )
        
        self._record_history(
            db=db,
            alert_config=alert_config,
            watched_api=watched_api,
            version_history_id=None,
            alert_reason="endpoint_recovered",
            severity="info",
            endpoint_path=endpoint_path,
            http_method=http_method,
            payload={
                "endpoint_path": endpoint_path,
                "http_method": http_method
            },
            status="sent" if success else "failed",
            error_message=None if success else "Failed to send email"
        )
        
        return success
    
    def _send_email(self, to: str, subject: str, html_body: str) -> bool:
        """
        Send an email via SMTP.
        
        Args:
            to: Recipient email address
            subject: Email subject
            html_body: HTML body content
            
        Returns:
            True if sent successfully
        """
        try:
            # Create message
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = f"{self.from_name} <{self.from_email}>"
            msg['To'] = to
            
            # Add HTML body
            msg.attach(MIMEText(html_body, 'html'))
            
            # Connect and send
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                if self.smtp_use_tls:
                    server.starttls()
                
                if self.smtp_username and self.smtp_password:
                    server.login(self.smtp_username, self.smtp_password)
                
                server.send_message(msg)
            
            logger.info(f"Sent email to {to}: {subject}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send email to {to}: {e}", exc_info=True)
            return False
    
    def _record_history(
        self,
        db: Session,
        alert_config: Any,
        watched_api: Any,
        version_history_id: Optional[int],
        alert_reason: str,
        severity: str,
        payload: Dict[str, Any],
        status: str,
        error_message: Optional[str],
        endpoint_path: Optional[str] = None,
        http_method: Optional[str] = None
    ):
        """Record alert in alert_history table."""
        try:
            history = AlertHistory(
                tenant_id=watched_api.tenant_id,
                watched_api_id=watched_api.id,
                alert_config_id=alert_config.id,
                version_history_id=version_history_id,
                alert_reason=alert_reason,
                severity=severity,
                endpoint_path=endpoint_path,
                http_method=http_method,
                payload=payload,
                status=status,
                error_message=error_message,
                sent_at=datetime.utcnow() if status == "sent" else None
            )
            
            db.add(history)
            db.commit()
            
            logger.debug(f"Recorded alert history: {alert_reason}")
            
        except Exception as e:
            logger.error(f"Failed to record alert history: {e}", exc_info=True)
            db.rollback()