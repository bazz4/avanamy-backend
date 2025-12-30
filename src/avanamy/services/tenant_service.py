from sqlalchemy.orm import Session
from avanamy.models.tenant import Tenant
from clerk_backend_api import Clerk
import os
import logging

logger = logging.getLogger(__name__)

clerk = Clerk(bearer_auth=os.getenv("CLERK_SECRET_KEY"))


def get_or_create_tenant(
    db: Session, 
    tenant_id: str,  # Clerk user_id or org_id (string)
    name: str,
    is_organization: bool = False
) -> Tenant:
    """
    Get existing tenant or create new one.
    tenant_id is a Clerk user_id or org_id (string).
    """
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    
    if tenant:
        logger.debug(f"Found existing tenant: {tenant.id}")
        return tenant
    
    # Create new tenant
    tenant = Tenant(
        id=tenant_id,  # Clerk's ID (string)
        name=name,
        slug=tenant_id[:8],  # First 8 chars
        is_organization=is_organization,
    )
    
    db.add(tenant)
    db.commit()
    db.refresh(tenant)
    
    logger.info(f"Created new {'org' if is_organization else 'personal'} tenant: {tenant.id} ({name})")
    return tenant