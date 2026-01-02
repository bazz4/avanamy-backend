"""
Provider CRUD endpoints.
"""
from typing import List
from datetime import datetime
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field, field_validator
import uuid

from avanamy.db.database import get_db
from avanamy.models.provider import Provider
from avanamy.auth.clerk import get_current_tenant_id

router = APIRouter(prefix="/providers", tags=["providers"])


# Pydantic Schemas
class ProviderCreate(BaseModel):
    """Schema for creating a provider."""
    name: str = Field(..., min_length=1, max_length=255)
    slug: str = Field(..., min_length=1, max_length=255)
    website: str | None = Field(None, max_length=500)
    logo_url: str | None = Field(None, max_length=500)
    description: str | None = None


class ProviderUpdate(BaseModel):
    """Schema for updating a provider."""
    name: str | None = Field(None, min_length=1, max_length=255)
    slug: str | None = Field(None, min_length=1, max_length=255)
    website: str | None = Field(None, max_length=500)
    logo_url: str | None = Field(None, max_length=500)
    description: str | None = None


class ProviderResponse(BaseModel):
    """Schema for provider response."""
    id: str
    tenant_id: str
    name: str
    slug: str
    website: str | None = None
    logo_url: str | None = None
    description: str | None = None
    created_at: str
    updated_at: str | None = None
    created_by_user_id: str | None = None
    updated_by_user_id: str | None = None

    class Config:
        from_attributes = True

    @field_validator('id', 'tenant_id', 'created_by_user_id', 'updated_by_user_id', mode='before')
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
@router.get("", response_model=List[ProviderResponse])
async def list_providers(
    tenant_id: str = Depends(get_current_tenant_id),
    db: Session = Depends(get_db)
):
    """List all providers for the current tenant."""
    providers = db.query(Provider).filter(
        Provider.tenant_id == tenant_id
    ).order_by(Provider.name).all()
    
    return providers


@router.get("/{provider_id}", response_model=ProviderResponse)
async def get_provider(
    provider_id: str,
    tenant_id: str = Depends(get_current_tenant_id),
    db: Session = Depends(get_db)
):
    """Get a specific provider."""
    provider = db.query(Provider).filter(
        Provider.id == provider_id,
        Provider.tenant_id == tenant_id
    ).first()
    
    if not provider:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Provider {provider_id} not found"
        )
    
    return provider


@router.post("", response_model=ProviderResponse, status_code=status.HTTP_201_CREATED)
async def create_provider(
    provider_data: ProviderCreate,
    tenant_id: str = Depends(get_current_tenant_id),
    db: Session = Depends(get_db)
):
    """Create a new provider."""
    # Check if slug already exists for this tenant
    existing = db.query(Provider).filter(
        Provider.tenant_id == tenant_id,
        Provider.slug == provider_data.slug
    ).first()
    
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Provider with slug '{provider_data.slug}' already exists"
        )
    
    # Clean data - convert empty strings to None
    website = provider_data.website.strip() if provider_data.website else None
    logo_url = provider_data.logo_url.strip() if provider_data.logo_url else None
    description = provider_data.description.strip() if provider_data.description else None
    
    # Create provider
    provider = Provider(
        id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        name=provider_data.name.strip(),
        slug=provider_data.slug.strip(),
        website=website if website else None,
        logo_url=logo_url if logo_url else None,
        description=description if description else None,
        created_by_user_id=tenant_id,
        updated_by_user_id=tenant_id
    )
    
    db.add(provider)
    db.commit()
    db.refresh(provider)
    
    return provider


@router.put("/{provider_id}", response_model=ProviderResponse)
async def update_provider(
    provider_id: str,
    provider_data: ProviderUpdate,
    tenant_id: str = Depends(get_current_tenant_id),
    db: Session = Depends(get_db)
):
    """Update a provider."""
    provider = db.query(Provider).filter(
        Provider.id == provider_id,
        Provider.tenant_id == tenant_id
    ).first()
    
    if not provider:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Provider {provider_id} not found"
        )
    
    # Check if slug is being changed and if it conflicts
    if provider_data.slug and provider_data.slug != provider.slug:
        existing = db.query(Provider).filter(
            Provider.tenant_id == tenant_id,
            Provider.slug == provider_data.slug,
            Provider.id != provider_id
        ).first()
        
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Provider with slug '{provider_data.slug}' already exists"
            )
    
    # Update fields
    update_data = provider_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(provider, field, value)
    
    provider.updated_by_user_id = tenant_id  # Using tenant_id as user_id for now
    
    db.commit()
    db.refresh(provider)
    
    return provider


@router.delete("/{provider_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_provider(
    provider_id: str,
    tenant_id: str = Depends(get_current_tenant_id),
    db: Session = Depends(get_db)
):
    """Delete a provider."""
    provider = db.query(Provider).filter(
        Provider.id == provider_id,
        Provider.tenant_id == tenant_id
    ).first()
    
    if not provider:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Provider {provider_id} not found"
        )
    
    # Check if provider has any API products
    # (This prevents deleting providers with existing products)
    # You can remove this check if you want cascade delete
    from avanamy.models.api_product import ApiProduct
    has_products = db.query(ApiProduct).filter(
        ApiProduct.provider_id == provider_id
    ).first()
    
    if has_products:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete provider with existing API products. Delete products first."
        )
    
    db.delete(provider)
    db.commit()
    
    return None