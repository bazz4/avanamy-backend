# src/avanamy/api/routes/providers.py

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from uuid import UUID

from avanamy.db.database import SessionLocal
from avanamy.auth.clerk import get_current_tenant_id
from avanamy.models.provider import Provider
from avanamy.models.api_product import ApiProduct

from opentelemetry import trace
import logging

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)

router = APIRouter(
    prefix="/providers",
    tags=["Providers"],
)

# ----------------------------------------
# DB dependency
# ----------------------------------------
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ----------------------------------------
# Pydantic models
# ----------------------------------------
from pydantic import BaseModel


class ProviderOut(BaseModel):
    id: UUID
    tenant_id: UUID
    name: str
    slug: str
    description: str | None = None

    class Config:
        from_attributes = True


class ApiProductOut(BaseModel):
    id: UUID
    tenant_id: UUID
    provider_id: UUID
    name: str
    slug: str
    description: str | None = None

    class Config:
        from_attributes = True


# ----------------------------------------
# GET /providers
# ----------------------------------------
@router.get("", response_model=list[ProviderOut])
async def list_providers(
    tenant_id: str = Depends(get_current_tenant_id),
    db: Session = Depends(get_db),
):
    """
    List all providers for this tenant.
    """
    with tracer.start_as_current_span("api.list_providers") as span:
        span.set_attribute("tenant.id", tenant_id)

        providers = (
            db.query(Provider)
            .filter(Provider.tenant_id == tenant_id)
            .order_by(Provider.name.asc())
            .all()
        )

        logger.info("Fetched %d providers for tenant=%s", len(providers), tenant_id)

        return providers


# ----------------------------------------
# GET /providers/{provider_id}
# ----------------------------------------
@router.get("/{provider_id}", response_model=ProviderOut)
async def get_provider(
    provider_id: UUID,
    tenant_id: str = Depends(get_current_tenant_id),
    db: Session = Depends(get_db),
):
    """
    Retrieve a single provider (tenant-scoped).
    """
    with tracer.start_as_current_span("api.get_provider") as span:
        span.set_attribute("tenant.id", tenant_id)
        span.set_attribute("provider.id", str(provider_id))

        provider = (
            db.query(Provider)
            .filter(
                Provider.id == provider_id,
                Provider.tenant_id == tenant_id,
            )
            .first()
        )

        if not provider:
            logger.warning(
                "Provider not found provider_id=%s tenant=%s",
                provider_id,
                tenant_id,
            )
            raise HTTPException(status_code=404, detail="Provider not found")

        return provider


# ----------------------------------------
# GET /providers/{provider_id}/products
# ----------------------------------------
@router.get("/{provider_id}/products", response_model=list[ApiProductOut])
async def list_provider_products(
    provider_id: UUID,
    tenant_id: str = Depends(get_current_tenant_id),
    db: Session = Depends(get_db),
):
    """
    List all API products under a given provider.
    """
    with tracer.start_as_current_span("api.list_provider_products") as span:
        span.set_attribute("tenant.id", tenant_id)
        span.set_attribute("provider.id", str(provider_id))

        # Verify provider exists
        provider = (
            db.query(Provider)
            .filter(
                Provider.id == provider_id,
                Provider.tenant_id == tenant_id,
            )
            .first()
        )
        if not provider:
            raise HTTPException(status_code=404, detail="Provider not found")

        products = (
            db.query(ApiProduct)
            .filter(
                ApiProduct.provider_id == provider_id,
                ApiProduct.tenant_id == tenant_id,
            )
            .order_by(ApiProduct.name.asc())
            .all()
        )

        logger.info(
            "Fetched %d products for provider=%s tenant=%s",
            len(products),
            provider_id,
            tenant_id,
        )

        return products
