from fastapi import Header, HTTPException, status
from typing import Optional


def get_tenant_id(x_tenant_id: Optional[str] = Header(None)):
    """
    Extract tenant ID from X-Tenant-ID header.
    Currently required for all tenant-aware routes.
    """
    if not x_tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-Tenant-ID header is required"
        )

    return x_tenant_id
