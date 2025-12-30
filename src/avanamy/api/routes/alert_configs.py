"""
API routes for managing alert configurations.

Endpoints:
- POST /alert-configs - Create a new alert configuration
- GET /alert-configs - List all alert configs for a tenant
- GET /alert-configs/{id} - Get a specific alert config
- PATCH /alert-configs/{id} - Update alert settings
- DELETE /alert-configs/{id} - Delete alert config
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, HttpUrl
from sqlalchemy.orm import Session
from typing import List, Optional
from uuid import UUID
from datetime import datetime

from avanamy.db.database import get_db
from avanamy.models.alert_configuration import AlertConfiguration
from avanamy.auth.clerk import get_current_tenant_id
from opentelemetry import trace

router = APIRouter(prefix="/alert-configs", tags=["alert-configs"])
tracer = trace.get_tracer(__name__)


# Request/Response Models

class CreateAlertConfigRequest(BaseModel):
    """Request to create a new alert configuration."""
    watched_api_id: UUID
    alert_type: str  # email, webhook, slack
    destination: str  # email address, webhook URL, or slack channel
    alert_on_breaking_changes: bool = True
    alert_on_non_breaking_changes: bool = False
    alert_on_endpoint_failures: bool = True
    alert_on_endpoint_recovery: bool = False
    enabled: bool = True
    
    class Config:
        json_schema_extra = {
            "example": {
                "watched_api_id": "123e4567-e89b-12d3-a456-426614174000",
                "alert_type": "email",
                "destination": "alerts@company.com",
                "alert_on_breaking_changes": True,
                "alert_on_endpoint_failures": True,
                "enabled": True
            }
        }


class UpdateAlertConfigRequest(BaseModel):
    """Request to update alert configuration settings."""
    alert_on_breaking_changes: Optional[bool] = None
    alert_on_non_breaking_changes: Optional[bool] = None
    alert_on_endpoint_failures: Optional[bool] = None
    alert_on_endpoint_recovery: Optional[bool] = None
    enabled: Optional[bool] = None
    destination: Optional[str] = None


class AlertConfigResponse(BaseModel):
    """Response model for alert configuration."""
    id: UUID
    tenant_id: UUID
    watched_api_id: UUID
    alert_type: str
    destination: str
    alert_on_breaking_changes: bool
    alert_on_non_breaking_changes: bool
    alert_on_endpoint_failures: bool
    alert_on_endpoint_recovery: bool
    enabled: bool
    created_at: datetime
    updated_at: Optional[datetime]
    
    class Config:
        from_attributes = True


# Endpoints

@router.post("", response_model=AlertConfigResponse, status_code=status.HTTP_201_CREATED)
async def create_alert_config(
    request: CreateAlertConfigRequest,
    tenant_id: str = Depends(get_current_tenant_id),
    db: Session = Depends(get_db)
):
    """
    Create a new alert configuration.
    
    Sets up where to send alerts (email, webhook, or Slack) and what to alert on.
    """
    with tracer.start_as_current_span("create_alert_config"):
        # Validate alert_type
        valid_types = ["email", "webhook", "slack"]
        if request.alert_type not in valid_types:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid alert_type. Must be one of: {', '.join(valid_types)}"
            )
        
        # TODO: Validate that watched_api exists and belongs to tenant
        
        # Create alert config
        alert_config = AlertConfiguration(
            tenant_id=tenant_id,
            watched_api_id=request.watched_api_id,
            alert_type=request.alert_type,
            destination=request.destination,
            alert_on_breaking_changes=request.alert_on_breaking_changes,
            alert_on_non_breaking_changes=request.alert_on_non_breaking_changes,
            alert_on_endpoint_failures=request.alert_on_endpoint_failures,
            alert_on_endpoint_recovery=request.alert_on_endpoint_recovery,
            enabled=request.enabled
        )
        
        db.add(alert_config)
        db.commit()
        db.refresh(alert_config)
        
        return alert_config


@router.get("", response_model=List[AlertConfigResponse])
async def list_alert_configs(
    watched_api_id: Optional[UUID] = None,
    tenant_id: str = Depends(get_current_tenant_id),
    db: Session = Depends(get_db)
):
    """
    List all alert configurations for the current tenant.
    
    Optionally filter by watched_api_id.
    """
    with tracer.start_as_current_span("list_alert_configs"):
        query = db.query(AlertConfiguration).filter(
            AlertConfiguration.tenant_id == tenant_id
        )
        
        if watched_api_id:
            query = query.filter(AlertConfiguration.watched_api_id == watched_api_id)
        
        configs = query.order_by(AlertConfiguration.created_at.desc()).all()
        
        return configs


@router.get("/{config_id}", response_model=AlertConfigResponse)
async def get_alert_config(
    config_id: UUID,
    tenant_id: str = Depends(get_current_tenant_id),
    db: Session = Depends(get_db)
):
    """Get details of a specific alert configuration."""
    with tracer.start_as_current_span("get_alert_config"):
        config = db.query(AlertConfiguration).filter(
            AlertConfiguration.id == config_id,
            AlertConfiguration.tenant_id == tenant_id
        ).first()
        
        if not config:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Alert configuration not found"
            )
        
        return config


@router.patch("/{config_id}", response_model=AlertConfigResponse)
async def update_alert_config(
    config_id: UUID,
    request: UpdateAlertConfigRequest,
    tenant_id: str = Depends(get_current_tenant_id),
    db: Session = Depends(get_db)
):
    """
    Update alert configuration settings.
    
    Can update:
    - What to alert on (breaking changes, endpoint failures, etc.)
    - Enable/disable the config
    - Change destination
    """
    with tracer.start_as_current_span("update_alert_config"):
        config = db.query(AlertConfiguration).filter(
            AlertConfiguration.id == config_id,
            AlertConfiguration.tenant_id == tenant_id
        ).first()
        
        if not config:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Alert configuration not found"
            )
        
        # Update fields if provided
        if request.alert_on_breaking_changes is not None:
            config.alert_on_breaking_changes = request.alert_on_breaking_changes
        
        if request.alert_on_non_breaking_changes is not None:
            config.alert_on_non_breaking_changes = request.alert_on_non_breaking_changes
        
        if request.alert_on_endpoint_failures is not None:
            config.alert_on_endpoint_failures = request.alert_on_endpoint_failures
        
        if request.alert_on_endpoint_recovery is not None:
            config.alert_on_endpoint_recovery = request.alert_on_endpoint_recovery
        
        if request.enabled is not None:
            config.enabled = request.enabled
        
        if request.destination is not None:
            config.destination = request.destination
        
        db.commit()
        db.refresh(config)
        
        return config


@router.delete("/{config_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_alert_config(
    config_id: UUID,
    tenant_id: str = Depends(get_current_tenant_id),
    db: Session = Depends(get_db)
):
    """Delete an alert configuration."""
    with tracer.start_as_current_span("delete_alert_config"):
        config = db.query(AlertConfiguration).filter(
            AlertConfiguration.id == config_id,
            AlertConfiguration.tenant_id == tenant_id
        ).first()
        
        if not config:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Alert configuration not found"
            )
        
        db.delete(config)
        db.commit()


@router.get("/{config_id}/test", response_model=dict)
async def test_alert_config(
    config_id: UUID,
    tenant_id: str = Depends(get_current_tenant_id),
    db: Session = Depends(get_db)
):
    """
    Send a test alert to verify configuration is working.
    
    Useful for testing email/webhook/slack setup before actual alerts.
    """
    with tracer.start_as_current_span("test_alert_config"):
        config = db.query(AlertConfiguration).filter(
            AlertConfiguration.id == config_id,
            AlertConfiguration.tenant_id == tenant_id
        ).first()
        
        if not config:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Alert configuration not found"
            )
        
        # Send test alert
        from avanamy.services.alert_service import AlertService
        alert_service = AlertService(db)
        
        test_payload = {
            "type": "test",
            "severity": "info",
            "subject": "🧪 Test Alert from Avanamy",
            "text": "This is a test alert to verify your configuration is working.",
            "details": {
                "alert_type": config.alert_type,
                "destination": config.destination,
                "timestamp": datetime.now().isoformat()
            },
            "body": """
            <html>
            <body>
                <h2>🧪 Test Alert</h2>
                <p>This is a test alert from Avanamy to verify your alert configuration is working correctly.</p>
                <p><strong>Alert Type:</strong> {}</p>
                <p><strong>Destination:</strong> {}</p>
                <p>If you received this, your alerts are configured properly!</p>
            </body>
            </html>
            """.format(config.alert_type, config.destination)
        }
        
        try:
            if config.alert_type == "email":
                await alert_service._send_email_alert(config.destination, test_payload)
            elif config.alert_type == "webhook":
                await alert_service._send_webhook_alert(config.destination, test_payload)
            elif config.alert_type == "slack":
                await alert_service._send_slack_alert(config.destination, test_payload)
            
            return {
                "status": "success",
                "message": f"Test alert sent to {config.destination}"
            }
        except Exception as e:
            return {
                "status": "failed",
                "message": f"Failed to send test alert: {str(e)}"
            }