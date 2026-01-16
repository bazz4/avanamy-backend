"""
API routes for alert history.

Endpoints:
- GET /alert-history - List all alert history with filtering
- GET /alert-history/{id} - Get details of a specific alert
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session, joinedload
from typing import List, Optional
from uuid import UUID
from datetime import datetime

from avanamy.db.database import get_db
from avanamy.models.alert_history import AlertHistory
from avanamy.models.watched_api import WatchedAPI
from avanamy.models.provider import Provider
from avanamy.models.api_product import ApiProduct
from avanamy.auth.clerk import get_current_tenant_id
from opentelemetry import trace

router = APIRouter(prefix="/alert-history", tags=["alert-history"])
tracer = trace.get_tracer(__name__)


# Response Models

class AlertHistoryResponse(BaseModel):
    """Response model for alert history."""
    id: UUID
    tenant_id: str
    watched_api_id: UUID
    alert_config_id: UUID
    provider_name: Optional[str] = None
    product_name: Optional[str] = None
    alert_reason: str
    severity: str
    endpoint_path: Optional[str] = None
    http_method: Optional[str] = None
    payload: Optional[dict] = None
    status: str
    error_message: Optional[str] = None
    sent_at: Optional[datetime] = None
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)


# Endpoints

@router.get("", response_model=List[AlertHistoryResponse])
async def list_alert_history(
    tenant_id: str = Depends(get_current_tenant_id),
    watched_api_id: Optional[UUID] = Query(None, description="Filter by watched API"),
    severity: Optional[str] = Query(None, description="Filter by severity: info, warning, critical"),
    status: Optional[str] = Query(None, description="Filter by status: pending, sent, failed"),
    limit: int = Query(100, description="Maximum number of results", le=500),
    db: Session = Depends(get_db)
):
    """
    List alert history for the current tenant.
    
    Supports filtering by watched_api_id, severity, and status.
    Returns most recent alerts first.
    """
    with tracer.start_as_current_span("list_alert_history"):
        # Build query with joins
        query = db.query(
            AlertHistory,
            Provider.name.label("provider_name"),
            ApiProduct.name.label("product_name")
        ).join(
            WatchedAPI, AlertHistory.watched_api_id == WatchedAPI.id
        ).outerjoin(
            Provider, WatchedAPI.provider_id == Provider.id
        ).outerjoin(
            ApiProduct, WatchedAPI.api_product_id == ApiProduct.id
        ).filter(
            AlertHistory.tenant_id == tenant_id
        )
        
        # Apply filters
        if watched_api_id:
            query = query.filter(AlertHistory.watched_api_id == watched_api_id)
        
        if severity:
            query = query.filter(AlertHistory.severity == severity)
        
        if status:
            query = query.filter(AlertHistory.status == status)
        
        # Order by most recent first and limit
        alerts = query.order_by(AlertHistory.created_at.desc()).limit(limit).all()
        
        # Convert to response format
        result = []
        for alert, provider_name, product_name in alerts:
            alert_dict = {
                "id": alert.id,
                "tenant_id": alert.tenant_id,
                "watched_api_id": alert.watched_api_id,
                "alert_config_id": alert.alert_config_id,
                "provider_name": provider_name,
                "product_name": product_name,
                "alert_reason": alert.alert_reason,
                "severity": alert.severity,
                "endpoint_path": alert.endpoint_path,
                "http_method": alert.http_method,
                "payload": alert.payload,
                "status": alert.status,
                "error_message": alert.error_message,
                "sent_at": alert.sent_at,
                "created_at": alert.created_at
            }
            result.append(AlertHistoryResponse(**alert_dict))
        
        return result


@router.get("/{alert_id}", response_model=AlertHistoryResponse)
async def get_alert_history(
    alert_id: UUID,
    tenant_id: str = Depends(get_current_tenant_id),
    db: Session = Depends(get_db)
):
    """Get details of a specific alert."""
    with tracer.start_as_current_span("get_alert_history"):
        # Query with joins
        result = db.query(
            AlertHistory,
            Provider.name.label("provider_name"),
            ApiProduct.name.label("product_name")
        ).join(
            WatchedAPI, AlertHistory.watched_api_id == WatchedAPI.id
        ).outerjoin(
            Provider, WatchedAPI.provider_id == Provider.id
        ).outerjoin(
            ApiProduct, WatchedAPI.api_product_id == ApiProduct.id
        ).filter(
            AlertHistory.id == alert_id,
            AlertHistory.tenant_id == tenant_id
        ).first()
        
        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Alert not found"
            )
        
        alert, provider_name, product_name = result
        
        alert_dict = {
            "id": alert.id,
            "tenant_id": alert.tenant_id,
            "watched_api_id": alert.watched_api_id,
            "alert_config_id": alert.alert_config_id,
            "provider_name": provider_name,
            "product_name": product_name,
            "alert_reason": alert.alert_reason,
            "severity": alert.severity,
            "endpoint_path": alert.endpoint_path,
            "http_method": alert.http_method,
            "payload": alert.payload,
            "status": alert.status,
            "error_message": alert.error_message,
            "sent_at": alert.sent_at,
            "created_at": alert.created_at
        }
        
        return AlertHistoryResponse(**alert_dict)
