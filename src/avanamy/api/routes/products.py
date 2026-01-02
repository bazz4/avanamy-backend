"""
API Product CRUD endpoints.
"""
from typing import List
from datetime import datetime
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field, field_validator
import uuid

from avanamy.db.database import get_db
from avanamy.models.api_product import ApiProduct
from avanamy.models.provider import Provider
from avanamy.auth.clerk import get_current_tenant_id

router = APIRouter(prefix="/api-products", tags=["api-products"])


# Pydantic Schemas
class ApiProductCreate(BaseModel):
    """Schema for creating an API product."""
    name: str = Field(..., min_length=1, max_length=255)
    slug: str = Field(..., min_length=1, max_length=255)
    provider_id: str = Field(..., description="UUID of the parent provider")
    description: str | None = None


class ApiProductUpdate(BaseModel):
    """Schema for updating an API product."""
    name: str | None = Field(None, min_length=1, max_length=255)
    slug: str | None = Field(None, min_length=1, max_length=255)
    provider_id: str | None = Field(None, description="UUID of the parent provider")
    description: str | None = None


class ApiProductResponse(BaseModel):
    """Schema for API product response."""
    id: str
    tenant_id: str
    provider_id: str
    name: str
    slug: str
    description: str | None = None
    created_at: str
    updated_at: str | None = None
    created_by_user_id: str | None = None
    updated_by_user_id: str | None = None
    # Include provider info
    provider_name: str | None = None
    provider_slug: str | None = None

    class Config:
        from_attributes = True

    @field_validator('id', 'tenant_id', 'provider_id', 'created_by_user_id', 'updated_by_user_id', mode='before')
    @classmethod
    def convert_uuid_to_str(cls, v):
        """Convert UUID objects to strings."""
        if isinstance(v, UUID):
            return str(v)
        return v
    
    @field_validator('created_at', 'updated_at', mode='before')
    @classmethod
    def convert_datetime_to_str(cls, v):
        """Convert datetime objects to ISO format strings."""
        if isinstance(v, datetime):
            return v.isoformat()
        return v


# Routes
@router.get("", response_model=List[ApiProductResponse])
async def list_api_products(
    provider_id: str | None = Query(None, description="Filter by provider ID"),
    tenant_id: str = Depends(get_current_tenant_id),
    db: Session = Depends(get_db)
):
    """List all API products for the current tenant, optionally filtered by provider."""
    query = db.query(ApiProduct).filter(ApiProduct.tenant_id == tenant_id)
    
    if provider_id:
        query = query.filter(ApiProduct.provider_id == provider_id)
    
    products = query.order_by(ApiProduct.name).all()
    
    # Enrich with provider info
    result = []
    for product in products:
        product_dict = {
            'id': product.id,
            'tenant_id': product.tenant_id,
            'provider_id': product.provider_id,
            'name': product.name,
            'slug': product.slug,
            'description': product.description,
            'created_at': product.created_at,
            'updated_at': product.updated_at,
            'created_by_user_id': product.created_by_user_id,
            'updated_by_user_id': product.updated_by_user_id,
            'provider_name': product.provider.name if product.provider else None,
            'provider_slug': product.provider.slug if product.provider else None,
        }
        result.append(ApiProductResponse(**product_dict))
    
    return result


@router.get("/{product_id}", response_model=ApiProductResponse)
async def get_api_product(
    product_id: str,
    tenant_id: str = Depends(get_current_tenant_id),
    db: Session = Depends(get_db)
):
    """Get a specific API product."""
    product = db.query(ApiProduct).filter(
        ApiProduct.id == product_id,
        ApiProduct.tenant_id == tenant_id
    ).first()
    
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"API Product {product_id} not found"
        )
    
    product_dict = {
        'id': product.id,
        'tenant_id': product.tenant_id,
        'provider_id': product.provider_id,
        'name': product.name,
        'slug': product.slug,
        'description': product.description,
        'created_at': product.created_at,
        'updated_at': product.updated_at,
        'created_by_user_id': product.created_by_user_id,
        'updated_by_user_id': product.updated_by_user_id,
        'provider_name': product.provider.name if product.provider else None,
        'provider_slug': product.provider.slug if product.provider else None,
    }
    
    return ApiProductResponse(**product_dict)


@router.post("", response_model=ApiProductResponse, status_code=status.HTTP_201_CREATED)
async def create_api_product(
    product_data: ApiProductCreate,
    tenant_id: str = Depends(get_current_tenant_id),
    db: Session = Depends(get_db)
):
    """Create a new API product."""
    # Verify provider exists and belongs to tenant
    provider = db.query(Provider).filter(
        Provider.id == product_data.provider_id,
        Provider.tenant_id == tenant_id
    ).first()
    
    if not provider:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Provider {product_data.provider_id} not found"
        )
    
    # Check if slug already exists for this provider
    existing = db.query(ApiProduct).filter(
        ApiProduct.provider_id == product_data.provider_id,
        ApiProduct.slug == product_data.slug
    ).first()
    
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"API Product with slug '{product_data.slug}' already exists for this provider"
        )
    
    # Clean data
    description = product_data.description.strip() if product_data.description else None
    
    # Create product
    product = ApiProduct(
        id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        provider_id=product_data.provider_id,
        name=product_data.name.strip(),
        slug=product_data.slug.strip(),
        description=description if description else None,
        created_by_user_id=tenant_id,
        updated_by_user_id=tenant_id
    )
    
    db.add(product)
    db.commit()
    db.refresh(product)
    
    product_dict = {
        'id': product.id,
        'tenant_id': product.tenant_id,
        'provider_id': product.provider_id,
        'name': product.name,
        'slug': product.slug,
        'description': product.description,
        'created_at': product.created_at,
        'updated_at': product.updated_at,
        'created_by_user_id': product.created_by_user_id,
        'updated_by_user_id': product.updated_by_user_id,
        'provider_name': provider.name,
        'provider_slug': provider.slug,
    }
    
    return ApiProductResponse(**product_dict)


@router.put("/{product_id}", response_model=ApiProductResponse)
async def update_api_product(
    product_id: str,
    product_data: ApiProductUpdate,
    tenant_id: str = Depends(get_current_tenant_id),
    db: Session = Depends(get_db)
):
    """Update an API product."""
    product = db.query(ApiProduct).filter(
        ApiProduct.id == product_id,
        ApiProduct.tenant_id == tenant_id
    ).first()
    
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"API Product {product_id} not found"
        )
    
    # If provider is being changed, verify it exists
    if product_data.provider_id and product_data.provider_id != str(product.provider_id):
        provider = db.query(Provider).filter(
            Provider.id == product_data.provider_id,
            Provider.tenant_id == tenant_id
        ).first()
        
        if not provider:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Provider {product_data.provider_id} not found"
            )
    
    # Check if slug is being changed and if it conflicts
    if product_data.slug and product_data.slug != product.slug:
        provider_id = product_data.provider_id or product.provider_id
        existing = db.query(ApiProduct).filter(
            ApiProduct.provider_id == provider_id,
            ApiProduct.slug == product_data.slug,
            ApiProduct.id != product_id
        ).first()
        
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"API Product with slug '{product_data.slug}' already exists for this provider"
            )
    
    # Update fields
    update_data = product_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if field == 'description':
            setattr(product, field, value.strip() if value else None)
        elif value is not None:
            setattr(product, field, value.strip() if isinstance(value, str) else value)
    
    product.updated_by_user_id = tenant_id
    
    db.commit()
    db.refresh(product)
    
    product_dict = {
        'id': product.id,
        'tenant_id': product.tenant_id,
        'provider_id': product.provider_id,
        'name': product.name,
        'slug': product.slug,
        'description': product.description,
        'created_at': product.created_at,
        'updated_at': product.updated_at,
        'created_by_user_id': product.created_by_user_id,
        'updated_by_user_id': product.updated_by_user_id,
        'provider_name': product.provider.name if product.provider else None,
        'provider_slug': product.provider.slug if product.provider else None,
    }
    
    return ApiProductResponse(**product_dict)


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_api_product(
    product_id: str,
    tenant_id: str = Depends(get_current_tenant_id),
    db: Session = Depends(get_db)
):
    """Delete an API product."""
    product = db.query(ApiProduct).filter(
        ApiProduct.id == product_id,
        ApiProduct.tenant_id == tenant_id
    ).first()
    
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"API Product {product_id} not found"
        )
    
    # Check if product has any API specs
    from avanamy.models.api_spec import ApiSpec
    has_specs = db.query(ApiSpec).filter(
        ApiSpec.api_product_id == product_id
    ).first()
    
    if has_specs:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete API product with existing API specs. Delete specs first."
        )
    
    db.delete(product)
    db.commit()
    
    return None