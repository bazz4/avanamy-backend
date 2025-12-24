"""
API routes for managing watched APIs.

Endpoints:
- POST /watched-apis - Add a new API to monitor
- GET /watched-apis - List all watched APIs for a tenant
- GET /watched-apis/{id} - Get details of a specific watched API
- PATCH /watched-apis/{id} - Update settings (enable/disable polling, change frequency)
- DELETE /watched-apis/{id} - Remove a watched API
- POST /watched-apis/{id}/poll - Trigger immediate poll
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, HttpUrl
from sqlalchemy.orm import Session
from typing import List, Optional
from uuid import UUID
from datetime import datetime

from avanamy.db.database import get_db
from avanamy.models.watched_api import WatchedAPI
from avanamy.models.provider import Provider
from avanamy.models.api_product import ApiProduct
from avanamy.services.polling_service import PollingService
from avanamy.services.polling_service import PollingService
from opentelemetry import trace

router = APIRouter(prefix="/watched-apis", tags=["watched-apis"])
tracer = trace.get_tracer(__name__)


# Request/Response Models

class CreateWatchedAPIRequest(BaseModel):
    """Request to create a new watched API."""
    provider_id: UUID
    api_product_id: UUID
    spec_url: HttpUrl
    polling_frequency: str = "daily"  # hourly, daily, weekly
    
    class Config:
        json_schema_extra = {
            "example": {
                "provider_id": "123e4567-e89b-12d3-a456-426614174000",
                "api_product_id": "123e4567-e89b-12d3-a456-426614174001",
                "spec_url": "https://raw.githubusercontent.com/stripe/openapi/master/openapi/spec3.yaml",
                "polling_frequency": "daily"
            }
        }


class UpdateWatchedAPIRequest(BaseModel):
    """Request to update watched API settings."""
    polling_enabled: Optional[bool] = None
    polling_frequency: Optional[str] = None
    status: Optional[str] = None


class WatchedAPIResponse(BaseModel):
    """Response model for watched API."""
    id: UUID
    tenant_id: UUID
    provider_id: UUID
    api_product_id: UUID
    api_spec_id: Optional[UUID] = None  # NEW
    provider_name: Optional[str] = None  # NEW
    product_name: Optional[str] = None   # NEW
    spec_url: str
    polling_frequency: str
    polling_enabled: bool
    last_polled_at: Optional[datetime]
    last_successful_poll_at: Optional[datetime]
    last_version_detected: Optional[int]
    consecutive_failures: int
    status: str
    created_at: datetime
    
    class Config:
        from_attributes = True


# Dependency to get tenant_id
# For MVP, we'll use a header. In Phase 4B (auth), this will come from JWT
def get_tenant_id(x_tenant_id: UUID = Depends(lambda: UUID("11111111-1111-1111-1111-111111111111"))):
    """Get tenant ID from request. For MVP, hardcoded. Will use JWT in Phase 4B."""
    return x_tenant_id


# Endpoints

@router.post("", response_model=WatchedAPIResponse, status_code=status.HTTP_201_CREATED)
def create_watched_api(
    request: CreateWatchedAPIRequest,
    tenant_id: UUID = Depends(get_tenant_id),
    db: Session = Depends(get_db)
):
    """
    Add a new external API to monitor.
    
    The system will:
    1. Validate the spec URL is accessible
    2. Create a WatchedAPI entry
    3. Optionally trigger an immediate poll (in background)
    """
    with tracer.start_as_current_span("create_watched_api"):
        # TODO: Validate that provider and api_product exist and belong to tenant
        
        watched_api = WatchedAPI(
            tenant_id=tenant_id,
            provider_id=request.provider_id,
            api_product_id=request.api_product_id,
            spec_url=str(request.spec_url),
            polling_frequency=request.polling_frequency,
            polling_enabled=True,
            status="active"
        )
        
        db.add(watched_api)
        db.commit()
        db.refresh(watched_api)
        
        return watched_api


@router.get("", response_model=List[WatchedAPIResponse])
def list_watched_apis(
    tenant_id: UUID = Depends(get_tenant_id),
    db: Session = Depends(get_db)
):
    """List all watched APIs for the current tenant."""
    with tracer.start_as_current_span("list_watched_apis"):
        # Join with Provider and ApiProduct to get names
        watched_apis = db.query(
            WatchedAPI,
            Provider.name.label("provider_name"),
            ApiProduct.name.label("product_name")
        ).outerjoin(
            Provider, WatchedAPI.provider_id == Provider.id
        ).outerjoin(
            ApiProduct, WatchedAPI.api_product_id == ApiProduct.id
        ).filter(
            WatchedAPI.tenant_id == tenant_id
        ).order_by(WatchedAPI.created_at.desc()).all()
        
        # Convert to response format
        result = []
        for watched_api, provider_name, product_name in watched_apis:
            api_dict = {
                "id": watched_api.id,
                "tenant_id": watched_api.tenant_id,
                "provider_id": watched_api.provider_id,
                "api_product_id": watched_api.api_product_id,
                "api_spec_id": watched_api.api_spec_id,
                "provider_name": provider_name,
                "product_name": product_name,
                "spec_url": watched_api.spec_url,
                "polling_frequency": watched_api.polling_frequency,
                "polling_enabled": watched_api.polling_enabled,
                "last_polled_at": watched_api.last_polled_at,
                "last_successful_poll_at": watched_api.last_successful_poll_at,
                "last_version_detected": watched_api.last_version_detected,
                "consecutive_failures": watched_api.consecutive_failures,
                "status": watched_api.status,
                "created_at": watched_api.created_at
            }
            result.append(WatchedAPIResponse(**api_dict))
        
        return result


@router.get("/{watched_api_id}", response_model=WatchedAPIResponse)
def get_watched_api(
    watched_api_id: UUID,
    tenant_id: UUID = Depends(get_tenant_id),
    db: Session = Depends(get_db)
):
    """Get details of a specific watched API."""
    with tracer.start_as_current_span("get_watched_api"):
        watched_api = db.query(WatchedAPI).filter(
            WatchedAPI.id == watched_api_id,
            WatchedAPI.tenant_id == tenant_id
        ).first()
        
        if not watched_api:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Watched API not found"
            )
        
        return watched_api


@router.patch("/{watched_api_id}", response_model=WatchedAPIResponse)
def update_watched_api(
    watched_api_id: UUID,
    request: UpdateWatchedAPIRequest,
    tenant_id: UUID = Depends(get_tenant_id),
    db: Session = Depends(get_db)
):
    """
    Update watched API settings.
    
    Can update:
    - polling_enabled (pause/resume polling)
    - polling_frequency (hourly, daily, weekly)
    - status (active, paused, failed)
    """
    with tracer.start_as_current_span("update_watched_api"):
        watched_api = db.query(WatchedAPI).filter(
            WatchedAPI.id == watched_api_id,
            WatchedAPI.tenant_id == tenant_id
        ).first()
        
        if not watched_api:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Watched API not found"
            )
        
        # Update fields if provided
        if request.polling_enabled is not None:
            watched_api.polling_enabled = request.polling_enabled
        
        if request.polling_frequency is not None:
            watched_api.polling_frequency = request.polling_frequency
        
        if request.status is not None:
            watched_api.status = request.status
        
        db.commit()
        db.refresh(watched_api)
        
        return watched_api


@router.delete("/{watched_api_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_watched_api(
    watched_api_id: UUID,
    tenant_id: UUID = Depends(get_tenant_id),
    db: Session = Depends(get_db)
):
    """Remove a watched API (soft delete by setting status to 'deleted')."""
    with tracer.start_as_current_span("delete_watched_api"):
        watched_api = db.query(WatchedAPI).filter(
            WatchedAPI.id == watched_api_id,
            WatchedAPI.tenant_id == tenant_id
        ).first()
        
        if not watched_api:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Watched API not found"
            )
        
        # Soft delete
        watched_api.status = "deleted"
        watched_api.polling_enabled = False
        
        db.commit()


@router.post("/{watched_api_id}/poll", response_model=dict)
async def trigger_poll(
    watched_api_id: UUID,
    tenant_id: UUID = Depends(get_tenant_id),
    db: Session = Depends(get_db)
):
    """
    Trigger an immediate poll of this watched API.
    
    Useful for testing or when you want to check for changes right away
    instead of waiting for the scheduled poll.
    """
    with tracer.start_as_current_span("trigger_poll"):
        watched_api = db.query(WatchedAPI).filter(
            WatchedAPI.id == watched_api_id,
            WatchedAPI.tenant_id == tenant_id
        ).first()
        
        if not watched_api:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Watched API not found"
            )
        
        # Run the poll
        service = PollingService(db)
        result = await service.poll_watched_api(watched_api_id)
        
        return result