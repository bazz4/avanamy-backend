# src/avanamy/api/routes/products.py

from __future__ import annotations

from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from avanamy.db.database import SessionLocal
from avanamy.api.dependencies.tenant import get_tenant_id
from avanamy.models.api_product import ApiProduct
from avanamy.models.api_spec import ApiSpec
from avanamy.models.provider import Provider

router = APIRouter(tags=["Products"])


# --- DB dependency -----------------------------------------------------------

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# --- Pydantic models ---------------------------------------------------------

class ProductOut(BaseModel):
    id: UUID
    name: str
    slug: str
    description: Optional[str] = None
    provider_id: UUID

    class Config:
        from_attributes = True


class SpecSummaryOut(BaseModel):
    id: UUID
    name: str
    version: Optional[str] = None
    description: Optional[str] = None

    class Config:
        from_attributes = True


# --- Helper serializers ------------------------------------------------------

def serialize_product(product: ApiProduct) -> Dict[str, Any]:
    return {
        "id": product.id,
        "name": product.name,
        "slug": product.slug,
        "description": getattr(product, "description", None),
        "provider_id": product.provider_id,
    }


def serialize_spec(spec: ApiSpec) -> Dict[str, Any]:
    return {
        "id": spec.id,
        "name": spec.name,
        "version": spec.version,
        "description": spec.description,
    }


# --- Endpoints ---------------------------------------------------------------

@router.get(
    "/providers/{provider_id}/products",
    response_model=List[ProductOut],
)
def list_products_for_provider(
    provider_id: UUID,
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
):
    """
    List all products for a provider, scoped to the current tenant.
    """
    # Ensure provider belongs to this tenant
    provider = (
        db.query(Provider)
        .filter(Provider.id == provider_id, Provider.tenant_id == tenant_id)
        .first()
    )
    if not provider:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Provider not found for this tenant",
        )

    products = (
        db.query(ApiProduct)
        .filter(ApiProduct.provider_id == provider_id)
        .order_by(ApiProduct.name.asc())
        .all()
    )

    return [serialize_product(p) for p in products]


@router.get(
    "/products/{product_id}/specs",
    response_model=List[SpecSummaryOut],
)
def list_specs_for_product(
    product_id: UUID,
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
):
    """
    List all API specs for a given product, scoped to the current tenant.
    """
    # Ensure product belongs to this tenant via provider → tenant
    product = (
        db.query(ApiProduct)
        .join(Provider, Provider.id == ApiProduct.provider_id)
        .filter(
            ApiProduct.id == product_id,
            Provider.tenant_id == tenant_id,
        )
        .first()
    )
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found for this tenant",
        )

    specs = (
        db.query(ApiSpec)
        .filter(ApiSpec.api_product_id == product_id)
        .order_by(ApiSpec.name.asc())
        .all()
    )

    return [serialize_spec(s) for s in specs]
