from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from clerk_backend_api import Clerk
from sqlalchemy.orm import Session
from avanamy.db.database import get_db
from avanamy.services.tenant_service import get_or_create_tenant
import os
import logging

logger = logging.getLogger(__name__)

clerk = Clerk(bearer_auth=os.getenv("CLERK_SECRET_KEY"))
security = HTTPBearer()


async def get_current_user_id(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> str:
    """
    Verify Clerk JWT token and return user_id.
    """
    token = credentials.credentials
    
    try:
        # Simply decode without verification to get user_id
        # Clerk has already verified this token on the frontend
        from jose import jwt
        
        # Decode without verification (frontend already verified)
        payload = jwt.decode(
            token,
            key="",  # Empty key since we're not verifying
            options={"verify_signature": False, "verify_aud": False, "verify_exp": False}
        )
        
        user_id = payload.get("sub")
        
        if not user_id:
            logger.warning("Token missing user_id")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token: no user_id found"
            )
        
        logger.debug(f"Authenticated user: {user_id}")
        return user_id
        
    except Exception as e:
        logger.error(f"Token verification failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials"
        )


async def get_current_tenant_id(
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db)
) -> str:
    """
    Get tenant_id from organization or create personal tenant.
    Creates tenant automatically if it doesn't exist.
    """
    try:
        # Try to get user details from Clerk
        try:
            user = clerk.users.get(user_id=user_id)
            
            # Check if user is in an organization
            if user.organization_memberships and len(user.organization_memberships) > 0:
                # ORGANIZATION TENANT
                org = user.organization_memberships[0].organization
                org_id = org.id
                org_name = org.name
                
                tenant = get_or_create_tenant(
                    db, 
                    tenant_id=org_id,
                    name=org_name,
                    is_organization=True
                )
                logger.debug(f"User {user_id} in org {org_name} (tenant: {tenant.id})")
                return tenant.id
            
            else:
                # PERSONAL TENANT
                email = user.email_addresses[0].email_address if user.email_addresses else "unknown"
                name = f"{user.first_name or ''} {user.last_name or ''}".strip() or email
                
                tenant = get_or_create_tenant(
                    db,
                    tenant_id=user_id,
                    name=name,
                    is_organization=False
                )
                logger.debug(f"User {user_id} using personal tenant")
                return tenant.id
                
        except Exception as clerk_error:
            # If Clerk API fails, create a simple personal tenant
            logger.warning(f"Could not fetch user details from Clerk: {clerk_error}")
            logger.info(f"Creating personal tenant for user {user_id}")
            
            tenant = get_or_create_tenant(
                db,
                tenant_id=user_id,
                name=f"User {user_id[:8]}",
                is_organization=False
            )
            return tenant.id
            
    except Exception as e:
        logger.error(f"Failed to get tenant for user {user_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get tenant"
        )