"""
Email service for sending alert notifications.

Supports multiple providers (Resend, SMTP) with easy switching.
"""

import logging
import os
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
from datetime import datetime, timezone

from sqlalchemy.orm import Session
from avanamy.models.alert_history import AlertHistory

logger = logging.getLogger(__name__)


# ============================================================================
# Email Provider Abstraction
# ============================================================================

class EmailProvider(ABC):
    """Abstract base class for email providers."""
    
    @abstractmethod
    def send(self, to: str, subject: str, html_body: str, from_email: str, from_name: str) -> bool:
        """
        Send an email.
        
        Args:
            to: Recipient email address
            subject: Email subject
            html_body: HTML body content
            from_email: Sender email address
            from_name: Sender name
            
        Returns:
            True if sent successfully
        """
        pass


class ResendProvider(EmailProvider):
    """Resend email provider."""
    
    def __init__(self, api_key: str):
        """Initialize Resend provider with API key."""
        self.api_key = api_key
        try:
            import resend
            resend.api_key = api_key
            self.resend = resend
        except ImportError:
            raise ImportError("Resend package not installed. Run: poetry add resend")
    
    def send(self, to: str, subject: str, html_body: str, from_email: str, from_name: str) -> bool:
        """Send email via Resend."""
        try:
            params = {
                "from": f"{from_name} <{from_email}>",
                "to": [to],
                "subject": subject,
                "html": html_body,
            }
            
            response = self.resend.Emails.send(params)
            logger.info(f"Sent email via Resend to {to}: {subject} (id: {response.get('id')})")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send email via Resend to {to}: {e}", exc_info=True)
            return False


class SMTPProvider(EmailProvider):
    """SMTP email provider (fallback)."""
    
    def __init__(self, host: str, port: int, username: str, password: str, use_tls: bool = True):
        """Initialize SMTP provider."""
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.use_tls = use_tls
    
    def send(self, to: str, subject: str, html_body: str, from_email: str, from_name: str) -> bool:
        """Send email via SMTP."""
        try:
            import smtplib
            from email.mime.text import MIMEText
            from email.mime.multipart import MIMEMultipart
            
            # Create message
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = f"{from_name} <{from_email}>"
            msg['To'] = to
            
            # Add HTML body
            msg.attach(MIMEText(html_body, 'html'))
            
            # Connect and send
            with smtplib.SMTP(self.host, self.port) as server:
                if self.use_tls:
                    server.starttls()
                
                if self.username and self.password:
                    server.login(self.username, self.password)
                
                server.send_message(msg)
            
            logger.info(f"Sent email via SMTP to {to}: {subject}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send email via SMTP to {to}: {e}", exc_info=True)
            return False


# ============================================================================
# Email Service
# ============================================================================

class EmailService:
    """
    Email service for sending notifications.
    
    Supports multiple providers via EMAIL_PROVIDER environment variable:
    - "resend" (default, recommended for production)
    - "smtp" (fallback, for self-hosted or testing)
    
    Resend Configuration:
    - RESEND_API_KEY: API key from resend.com
    - EMAIL_FROM: From email address (e.g., alerts@yourdomain.com)
    
    SMTP Configuration (fallback):
    - SMTP_HOST: SMTP server (default: localhost)
    - SMTP_PORT: SMTP port (default: 587)
    - SMTP_USERNAME: SMTP username
    - SMTP_PASSWORD: SMTP password
    - SMTP_USE_TLS: Use TLS (default: true)
    """
    
    def __init__(self):
        """Initialize email service with configured provider."""
        self.from_email = os.getenv("EMAIL_FROM", "alerts@avanamy.com")
        self.from_name = os.getenv("EMAIL_FROM_NAME", "Avanamy Alerts")
        self.frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
        
        # Initialize provider based on EMAIL_PROVIDER
        provider_type = os.getenv("EMAIL_PROVIDER", "resend").lower()
        
        if provider_type == "resend":
            api_key = os.getenv("RESEND_API_KEY")
            if not api_key:
                logger.warning("RESEND_API_KEY not set, emails will not be sent!")
                self.provider = None
            else:
                self.provider = ResendProvider(api_key)
                logger.info("Email service initialized with Resend provider")
        
        elif provider_type == "smtp":
            self.provider = SMTPProvider(
                host=os.getenv("SMTP_HOST", "localhost"),
                port=int(os.getenv("SMTP_PORT", "587")),
                username=os.getenv("SMTP_USERNAME", ""),
                password=os.getenv("SMTP_PASSWORD", ""),
                use_tls=os.getenv("SMTP_USE_TLS", "true").lower() == "true"
            )
            logger.info("Email service initialized with SMTP provider")
        
        else:
            logger.error(f"Unknown EMAIL_PROVIDER: {provider_type}")
            self.provider = None
    
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
        subject = f"🚨 Breaking Changes Detected - {watched_api.api_spec.name}"
        
        # Get product and provider info
        product = watched_api.api_product
        provider = product.provider if product else None
        
        body = self._get_breaking_change_template(
            api_name=watched_api.api_spec.name,
            provider_name=provider.name if provider else "Unknown",
            product_name=product.name if product else "Unknown",
            version=version.version,
            breaking_changes_count=breaking_changes_count,
            summary=version.summary,
            spec_url=f"{self.frontend_url}/specs/{watched_api.api_spec_id}",
            diff_url=f"{self.frontend_url}/specs/{watched_api.api_spec_id}/versions/{version.version}/diff"
        )
        
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
        subject = f"ℹ️ API Changes Detected - {watched_api.api_spec.name}"
        
        product = watched_api.api_product
        provider = product.provider if product else None
        
        body = self._get_non_breaking_change_template(
            api_name=watched_api.api_spec.name,
            provider_name=provider.name if provider else "Unknown",
            product_name=product.name if product else "Unknown",
            version=version.version,
            summary=version.summary,
            spec_url=f"{self.frontend_url}/specs/{watched_api.api_spec_id}",
            diff_url=f"{self.frontend_url}/specs/{watched_api.api_spec_id}/versions/{version.version}/diff"
        )
        
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
    
    def send_invitation_email(
        self,
        to_email: str,
        inviter_name: str,
        organization_name: str,
        invitation_token: str
    ) -> bool:
        """
        Send organization invitation email.
        
        Args:
            to_email: Invitee email address
            inviter_name: Name of person sending invite
            organization_name: Organization name
            invitation_token: Token for accepting invitation
            
        Returns:
            True if sent successfully
        """
        subject = f"{inviter_name} invited you to join {organization_name} on Avanamy"
        
        accept_url = f"{self.frontend_url}/invitations/accept?token={invitation_token}"
        decline_url = f"{self.frontend_url}/invitations/decline?token={invitation_token}"
        
        body = self._get_invitation_template(
            inviter_name=inviter_name,
            organization_name=organization_name,
            accept_url=accept_url,
            decline_url=decline_url
        )
        
        return self._send_email(
            to=to_email,
            subject=subject,
            html_body=body
        )
    
    def _send_email(self, to: str, subject: str, html_body: str) -> bool:
        """
        Send an email using configured provider.
        
        Args:
            to: Recipient email address
            subject: Email subject
            html_body: HTML body content
            
        Returns:
            True if sent successfully
        """
        if not self.provider:
            logger.warning(f"Email provider not configured, skipping email to {to}")
            return False
        
        return self.provider.send(
            to=to,
            subject=subject,
            html_body=html_body,
            from_email=self.from_email,
            from_name=self.from_name
        )
    
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
                sent_at=datetime.now(timezone.utc) if status == "sent" else None
            )
            
            db.add(history)
            db.commit()
            
            logger.debug(f"Recorded alert history: {alert_reason}")
            
        except Exception as e:
            logger.error(f"Failed to record alert history: {e}", exc_info=True)
            db.rollback()
    
    # ========================================================================
    # Email Templates
    # ========================================================================
    
    def _get_breaking_change_template(
        self,
        api_name: str,
        provider_name: str,
        product_name: str,
        version: int,
        breaking_changes_count: int,
        summary: Optional[str],
        spec_url: str,
        diff_url: str
    ) -> str:
        """Get HTML template for breaking change alert."""
        return f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Breaking Changes Detected</title>
</head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; line-height: 1.6; color: #334155; background-color: #f8fafc; margin: 0; padding: 0;">
    <div style="max-width: 600px; margin: 40px auto; background-color: #ffffff; border-radius: 8px; box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.1);">
        <!-- Header -->
        <div style="background: linear-gradient(135deg, #dc2626 0%, #991b1b 100%); color: white; padding: 32px; border-radius: 8px 8px 0 0;">
            <div style="font-size: 40px; margin-bottom: 8px;">🚨</div>
            <h1 style="margin: 0; font-size: 24px; font-weight: 600;">Breaking Changes Detected</h1>
            <p style="margin: 8px 0 0 0; opacity: 0.9; font-size: 14px;">{api_name}</p>
        </div>
        
        <!-- Content -->
        <div style="padding: 32px;">
            <div style="background-color: #fef2f2; border-left: 4px solid #dc2626; padding: 16px; border-radius: 4px; margin-bottom: 24px;">
                <p style="margin: 0; font-weight: 500; color: #991b1b;">
                    <strong>{breaking_changes_count}</strong> breaking change{'' if breaking_changes_count == 1 else 's'} detected in <strong>version {version}</strong>
                </p>
            </div>
            
            <div style="margin-bottom: 24px;">
                <h2 style="font-size: 16px; font-weight: 600; color: #1e293b; margin: 0 0 12px 0;">API Details</h2>
                <table style="width: 100%; border-collapse: collapse;">
                    <tr style="border-bottom: 1px solid #e2e8f0;">
                        <td style="padding: 8px 0; color: #64748b; font-size: 14px;">Provider</td>
                        <td style="padding: 8px 0; font-weight: 500; font-size: 14px;">{provider_name}</td>
                    </tr>
                    <tr style="border-bottom: 1px solid #e2e8f0;">
                        <td style="padding: 8px 0; color: #64748b; font-size: 14px;">Product</td>
                        <td style="padding: 8px 0; font-weight: 500; font-size: 14px;">{product_name}</td>
                    </tr>
                    <tr style="border-bottom: 1px solid #e2e8f0;">
                        <td style="padding: 8px 0; color: #64748b; font-size: 14px;">API</td>
                        <td style="padding: 8px 0; font-weight: 500; font-size: 14px;">{api_name}</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px 0; color: #64748b; font-size: 14px;">Version</td>
                        <td style="padding: 8px 0; font-weight: 500; font-size: 14px;">v{version}</td>
                    </tr>
                </table>
            </div>
            
            {f'''
            <div style="margin-bottom: 24px;">
                <h2 style="font-size: 16px; font-weight: 600; color: #1e293b; margin: 0 0 12px 0;">Summary</h2>
                <p style="margin: 0; color: #475569; font-size: 14px;">{summary}</p>
            </div>
            ''' if summary else ''}
            
            <div style="margin-bottom: 24px;">
                <a href="{diff_url}" style="display: inline-block; background-color: #7c3aed; color: white; text-decoration: none; padding: 12px 24px; border-radius: 6px; font-weight: 500; font-size: 14px;">
                    View Detailed Diff →
                </a>
            </div>
            
            <div style="border-top: 1px solid #e2e8f0; padding-top: 16px; margin-top: 24px;">
                <p style="margin: 0; font-size: 13px; color: #64748b;">
                    Need help? Check your <a href="{spec_url}" style="color: #7c3aed; text-decoration: none;">API dashboard</a> or view impact analysis to see which code will break.
                </p>
            </div>
        </div>
        
        <!-- Footer -->
        <div style="background-color: #f8fafc; padding: 24px 32px; border-radius: 0 0 8px 8px; border-top: 1px solid #e2e8f0;">
            <p style="margin: 0; font-size: 12px; color: #64748b;">
                You're receiving this because you configured alerts for this API.
                <br>
                Manage your notification settings in <a href="{self.frontend_url}/settings" style="color: #7c3aed; text-decoration: none;">Settings</a>.
            </p>
        </div>
    </div>
</body>
</html>
        """
    
    def _get_non_breaking_change_template(
        self,
        api_name: str,
        provider_name: str,
        product_name: str,
        version: int,
        summary: Optional[str],
        spec_url: str,
        diff_url: str
    ) -> str:
        """Get HTML template for non-breaking change alert."""
        return f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>API Changes Detected</title>
</head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; line-height: 1.6; color: #334155; background-color: #f8fafc; margin: 0; padding: 0;">
    <div style="max-width: 600px; margin: 40px auto; background-color: #ffffff; border-radius: 8px; box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.1);">
        <!-- Header -->
        <div style="background: linear-gradient(135deg, #0ea5e9 0%, #0284c7 100%); color: white; padding: 32px; border-radius: 8px 8px 0 0;">
            <div style="font-size: 40px; margin-bottom: 8px;">ℹ️</div>
            <h1 style="margin: 0; font-size: 24px; font-weight: 600;">API Changes Detected</h1>
            <p style="margin: 8px 0 0 0; opacity: 0.9; font-size: 14px;">{api_name}</p>
        </div>
        
        <!-- Content -->
        <div style="padding: 32px;">
            <div style="background-color: #f0f9ff; border-left: 4px solid #0ea5e9; padding: 16px; border-radius: 4px; margin-bottom: 24px;">
                <p style="margin: 0; font-weight: 500; color: #075985;">
                    Non-breaking changes detected in <strong>version {version}</strong>
                </p>
            </div>
            
            <div style="margin-bottom: 24px;">
                <h2 style="font-size: 16px; font-weight: 600; color: #1e293b; margin: 0 0 12px 0;">API Details</h2>
                <table style="width: 100%; border-collapse: collapse;">
                    <tr style="border-bottom: 1px solid #e2e8f0;">
                        <td style="padding: 8px 0; color: #64748b; font-size: 14px;">Provider</td>
                        <td style="padding: 8px 0; font-weight: 500; font-size: 14px;">{provider_name}</td>
                    </tr>
                    <tr style="border-bottom: 1px solid #e2e8f0;">
                        <td style="padding: 8px 0; color: #64748b; font-size: 14px;">Product</td>
                        <td style="padding: 8px 0; font-weight: 500; font-size: 14px;">{product_name}</td>
                    </tr>
                    <tr style="border-bottom: 1px solid #e2e8f0;">
                        <td style="padding: 8px 0; color: #64748b; font-size: 14px;">API</td>
                        <td style="padding: 8px 0; font-weight: 500; font-size: 14px;">{api_name}</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px 0; color: #64748b; font-size: 14px;">Version</td>
                        <td style="padding: 8px 0; font-weight: 500; font-size: 14px;">v{version}</td>
                    </tr>
                </table>
            </div>
            
            {f'''
            <div style="margin-bottom: 24px;">
                <h2 style="font-size: 16px; font-weight: 600; color: #1e293b; margin: 0 0 12px 0;">Summary</h2>
                <p style="margin: 0; color: #475569; font-size: 14px;">{summary}</p>
            </div>
            ''' if summary else ''}
            
            <div style="margin-bottom: 24px;">
                <a href="{diff_url}" style="display: inline-block; background-color: #7c3aed; color: white; text-decoration: none; padding: 12px 24px; border-radius: 6px; font-weight: 500; font-size: 14px;">
                    View Changes →
                </a>
            </div>
            
            <div style="border-top: 1px solid #e2e8f0; padding-top: 16px; margin-top: 24px;">
                <p style="margin: 0; font-size: 13px; color: #64748b;">
                    These changes should not affect your existing code. Review the <a href="{diff_url}" style="color: #7c3aed; text-decoration: none;">detailed diff</a> to see what's new.
                </p>
            </div>
        </div>
        
        <!-- Footer -->
        <div style="background-color: #f8fafc; padding: 24px 32px; border-radius: 0 0 8px 8px; border-top: 1px solid #e2e8f0;">
            <p style="margin: 0; font-size: 12px; color: #64748b;">
                You're receiving this because you configured alerts for this API.
                <br>
                Manage your notification settings in <a href="{self.frontend_url}/settings" style="color: #7c3aed; text-decoration: none;">Settings</a>.
            </p>
        </div>
    </div>
</body>
</html>
        """
    
    def _get_invitation_template(
        self,
        inviter_name: str,
        organization_name: str,
        accept_url: str,
        decline_url: str
    ) -> str:
        """Get HTML template for organization invitation."""
        return f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Organization Invitation</title>
</head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; line-height: 1.6; color: #334155; background-color: #f8fafc; margin: 0; padding: 0;">
    <div style="max-width: 600px; margin: 40px auto; background-color: #ffffff; border-radius: 8px; box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.1);">
        <!-- Header -->
        <div style="background: linear-gradient(135deg, #7c3aed 0%, #6d28d9 100%); color: white; padding: 32px; border-radius: 8px 8px 0 0;">
            <div style="font-size: 40px; margin-bottom: 8px;">👋</div>
            <h1 style="margin: 0; font-size: 24px; font-weight: 600;">You've been invited!</h1>
            <p style="margin: 8px 0 0 0; opacity: 0.9; font-size: 14px;">Join {organization_name} on Avanamy</p>
        </div>
        
        <!-- Content -->
        <div style="padding: 32px;">
            <p style="margin: 0 0 16px 0; font-size: 16px; color: #1e293b;">
                <strong>{inviter_name}</strong> has invited you to join <strong>{organization_name}</strong> on Avanamy.
            </p>
            
            <p style="margin: 0 0 24px 0; font-size: 14px; color: #475569;">
                Avanamy helps your team monitor API changes, detect breaking changes, and understand their impact on your codebase.
            </p>
            
            <div style="margin-bottom: 24px;">
                <a href="{accept_url}" style="display: inline-block; background-color: #7c3aed; color: white; text-decoration: none; padding: 12px 32px; border-radius: 6px; font-weight: 500; font-size: 14px; margin-right: 12px;">
                    Accept Invitation
                </a>
                <a href="{decline_url}" style="display: inline-block; background-color: #f1f5f9; color: #475569; text-decoration: none; padding: 12px 32px; border-radius: 6px; font-weight: 500; font-size: 14px;">
                    Decline
                </a>
            </div>
            
            <div style="border-top: 1px solid #e2e8f0; padding-top: 16px; margin-top: 24px;">
                <p style="margin: 0; font-size: 13px; color: #64748b;">
                    This invitation will expire in 7 days. If you don't want to join this organization, you can safely ignore this email.
                </p>
            </div>
        </div>
        
        <!-- Footer -->
        <div style="background-color: #f8fafc; padding: 24px 32px; border-radius: 0 0 8px 8px; border-top: 1px solid #e2e8f0;">
            <p style="margin: 0; font-size: 12px; color: #64748b;">
                If you have questions, visit <a href="{self.frontend_url}/help" style="color: #7c3aed; text-decoration: none;">Avanamy Help Center</a>.
            </p>
        </div>
    </div>
</body>
</html>
        """
