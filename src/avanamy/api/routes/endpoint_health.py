"""
API routes for endpoint health monitoring.

Endpoints:
- GET /watched-apis/{watched_api_id}/health - Get health metrics for all endpoints of a watched API
- GET /health/summary - Get overall health summary across all watched APIs
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func, desc, Integer
from typing import List, Optional
from uuid import UUID
from datetime import datetime, timedelta

from avanamy.db.database import get_db
from avanamy.models.endpoint_health import EndpointHealth
from avanamy.models.watched_api import WatchedAPI
from avanamy.models.provider import Provider
from avanamy.models.api_product import ApiProduct
from opentelemetry import trace

router = APIRouter(tags=["endpoint-health"])
tracer = trace.get_tracer(__name__)


# Response Models

class EndpointHealthResponse(BaseModel):
    """Response model for endpoint health check."""
    id: UUID
    watched_api_id: UUID
    endpoint_path: str
    http_method: str
    status_code: Optional[int]
    response_time_ms: Optional[int]
    is_healthy: bool
    error_message: Optional[str]
    checked_at: datetime
    
    class Config:
        from_attributes = True


class EndpointHealthSummary(BaseModel):
    """Summary statistics for an endpoint."""
    endpoint_path: str
    http_method: str
    total_checks: int
    healthy_checks: int
    uptime_percentage: float
    avg_response_time_ms: Optional[float]
    last_check: datetime
    is_currently_healthy: bool


class WatchedAPIHealthSummary(BaseModel):
    """Health summary for a watched API."""
    watched_api_id: UUID
    provider_name: Optional[str]
    product_name: Optional[str]
    total_endpoints: int
    healthy_endpoints: int
    avg_response_time_ms: Optional[float]
    uptime_percentage: float
    last_checked: datetime


# Dependency to get tenant_id
def get_tenant_id(x_tenant_id: UUID = Depends(lambda: UUID("11111111-1111-1111-1111-111111111111"))):
    """Get tenant ID from request. For MVP, hardcoded."""
    return x_tenant_id


# Endpoints

@router.get("/watched-apis/{watched_api_id}/health", response_model=List[EndpointHealthResponse])
def get_endpoint_health(
    watched_api_id: UUID,
    tenant_id: UUID = Depends(get_tenant_id),
    limit: int = Query(100, description="Number of recent checks per endpoint", le=1000),
    db: Session = Depends(get_db)
):
    """
    Get health check history for all endpoints of a watched API.
    
    Returns the most recent health checks for each endpoint.
    """
    with tracer.start_as_current_span("get_endpoint_health"):
        # Verify watched API belongs to tenant
        watched_api = db.query(WatchedAPI).filter(
            WatchedAPI.id == watched_api_id,
            WatchedAPI.tenant_id == tenant_id
        ).first()
        
        if not watched_api:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Watched API not found"
            )
        
        # Get recent health checks
        health_checks = db.query(EndpointHealth).filter(
            EndpointHealth.watched_api_id == watched_api_id
        ).order_by(desc(EndpointHealth.checked_at)).limit(limit).all()
        
        return health_checks


@router.get("/watched-apis/{watched_api_id}/health/summary", response_model=List[EndpointHealthSummary])
def get_endpoint_health_summary(
    watched_api_id: UUID,
    tenant_id: UUID = Depends(get_tenant_id),
    hours: int = Query(24, description="Time window in hours for statistics"),
    db: Session = Depends(get_db)
):
    """
    Get aggregated health statistics for each endpoint.
    
    Returns uptime percentage, average response time, etc.
    """
    with tracer.start_as_current_span("get_endpoint_health_summary"):
        # Verify watched API belongs to tenant
        watched_api = db.query(WatchedAPI).filter(
            WatchedAPI.id == watched_api_id,
            WatchedAPI.tenant_id == tenant_id
        ).first()
        
        if not watched_api:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Watched API not found"
            )
        
        # Calculate time window
        since = datetime.utcnow() - timedelta(hours=hours)
        
        # Get all unique endpoints
        endpoints = db.query(
            EndpointHealth.endpoint_path,
            EndpointHealth.http_method
        ).filter(
            EndpointHealth.watched_api_id == watched_api_id,
            EndpointHealth.checked_at >= since
        ).distinct().all()
        
        summaries = []
        for endpoint_path, http_method in endpoints:
            # Get stats for this endpoint
            stats = db.query(
                func.count(EndpointHealth.id).label('total_checks'),
                func.sum(func.cast(EndpointHealth.is_healthy, Integer)).label('healthy_checks'),
                func.avg(EndpointHealth.response_time_ms).label('avg_response_time'),
                func.max(EndpointHealth.checked_at).label('last_check')
            ).filter(
                EndpointHealth.watched_api_id == watched_api_id,
                EndpointHealth.endpoint_path == endpoint_path,
                EndpointHealth.http_method == http_method,
                EndpointHealth.checked_at >= since
            ).first()
            
            # Get most recent check to determine current health
            latest = db.query(EndpointHealth).filter(
                EndpointHealth.watched_api_id == watched_api_id,
                EndpointHealth.endpoint_path == endpoint_path,
                EndpointHealth.http_method == http_method
            ).order_by(desc(EndpointHealth.checked_at)).first()
            
            if stats.total_checks:
                uptime = (stats.healthy_checks / stats.total_checks) * 100
                summaries.append(EndpointHealthSummary(
                    endpoint_path=endpoint_path,
                    http_method=http_method,
                    total_checks=stats.total_checks,
                    healthy_checks=stats.healthy_checks,
                    uptime_percentage=round(uptime, 2),
                    avg_response_time_ms=round(stats.avg_response_time, 2) if stats.avg_response_time else None,
                    last_check=stats.last_check,
                    is_currently_healthy=latest.is_healthy if latest else False
                ))
        
        return summaries


@router.get("/health/summary", response_model=List[WatchedAPIHealthSummary])
def get_all_health_summary(
    tenant_id: UUID = Depends(get_tenant_id),
    hours: int = Query(24, description="Time window in hours for statistics"),
    db: Session = Depends(get_db)
):
    """
    Get health summary for all watched APIs.
    
    Useful for dashboard overview.
    """
    with tracer.start_as_current_span("get_all_health_summary"):
        # Get all watched APIs for tenant
        watched_apis = db.query(WatchedAPI).filter(
            WatchedAPI.tenant_id == tenant_id,
            WatchedAPI.polling_enabled == True
        ).all()
        
        since = datetime.utcnow() - timedelta(hours=hours)
        summaries = []
        
        for api in watched_apis:
            # Get provider and product names
            provider = db.query(Provider).filter(Provider.id == api.provider_id).first()
            product = db.query(ApiProduct).filter(ApiProduct.id == api.api_product_id).first()
            
            # Get stats for this watched API
            stats = db.query(
                func.count(EndpointHealth.id).label('total_checks'),
                func.sum(func.cast(EndpointHealth.is_healthy, Integer)).label('healthy_checks'),
                func.avg(EndpointHealth.response_time_ms).label('avg_response_time'),
                func.max(EndpointHealth.checked_at).label('last_check')
            ).filter(
                EndpointHealth.watched_api_id == api.id,
                EndpointHealth.checked_at >= since
            ).first()
            
            # Count unique endpoints
            unique_endpoints = db.query(
                func.count(func.distinct(
                    func.concat(EndpointHealth.endpoint_path, EndpointHealth.http_method)
                ))
            ).filter(
                EndpointHealth.watched_api_id == api.id,
                EndpointHealth.checked_at >= since
            ).scalar()
            
            # Count currently healthy endpoints
            healthy_endpoints = db.query(
                func.count(func.distinct(
                    func.concat(EndpointHealth.endpoint_path, EndpointHealth.http_method)
                ))
            ).filter(
                EndpointHealth.watched_api_id == api.id,
                EndpointHealth.is_healthy == True,
                EndpointHealth.checked_at >= since
            ).scalar()
            
            if stats.total_checks and stats.total_checks > 0:
                uptime = (stats.healthy_checks / stats.total_checks) * 100
                summaries.append(WatchedAPIHealthSummary(
                    watched_api_id=api.id,
                    provider_name=provider.name if provider else None,
                    product_name=product.name if product else None,
                    total_endpoints=unique_endpoints or 0,
                    healthy_endpoints=healthy_endpoints or 0,
                    avg_response_time_ms=round(stats.avg_response_time, 2) if stats.avg_response_time else None,
                    uptime_percentage=round(uptime, 2),
                    last_checked=stats.last_check
                ))
        
        return summaries