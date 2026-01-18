"""
Role-Based Access Control (RBAC) middleware for FastAPI.

Provides FastAPI dependencies for:
- Checking user permissions on routes
- Requiring specific roles
- Getting current user's role in context

Usage:
    @router.post("/providers")
    async def create_provider(
        _: None = Depends(require_permission(Permission.CREATE_PROVIDER)),
        tenant_id: str = Depends(get_current_tenant_id),
        ...
    ):
        ...
        
    @router.delete("/providers/{id}")
    async def delete_provider(
        _: None = Depends(require_role(Role.ADMIN)),
        ...
    ):
        ...
"""
import logging
from typing import Optional, Callable
from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from avanamy.auth.clerk import get_current_user_id, get_current_tenant_id
from avanamy.auth.permissions import Permission, Role, has_permission, is_role_at_least
from avanamy.db.database import get_db
from avanamy.models.organization_member import OrganizationMember

logger = logging.getLogger(__name__)


class UserContext:
    """
    Context object containing user information and role.
    
    Useful when you need both user_id and role in a route.
    """
    def __init__(
        self,
        user_id: str,
        tenant_id: str,
        role: Optional[str],
        member: Optional[OrganizationMember] = None
    ):
        self.user_id = user_id
        self.tenant_id = tenant_id
        self.role = role
        self.member = member
    
    def has_permission(self, permission: Permission) -> bool:
        """Check if user has a specific permission."""
        return has_permission(self.role, permission)
    
    def is_at_least(self, minimum_role: Role) -> bool:
        """Check if user's role is at least the minimum."""
        return is_role_at_least(self.role, minimum_role)
    
    @property
    def is_owner(self) -> bool:
        return self.role == Role.OWNER.value
    
    @property
    def is_admin(self) -> bool:
        return self.role in [Role.OWNER.value, Role.ADMIN.value]
    
    @property
    def is_developer(self) -> bool:
        return self.role in [Role.OWNER.value, Role.ADMIN.value, Role.DEVELOPER.value]


async def get_user_role(
    user_id: str = Depends(get_current_user_id),
    tenant_id: str = Depends(get_current_tenant_id),
    db: Session = Depends(get_db)
) -> Optional[str]:
    """
    Get the current user's role in the tenant.
    
    Returns None if user is not a member of the tenant.
    For personal tenants (non-organization), returns 'owner'.
    """
    from avanamy.models.tenant import Tenant
    
    # Check if this is a personal tenant (user_id == tenant_id)
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    
    if tenant and not tenant.is_organization:
        # Personal tenant - user is always owner
        return Role.OWNER.value
    
    # Organization tenant - look up membership
    member = db.query(OrganizationMember).filter(
        OrganizationMember.user_id == user_id,
        OrganizationMember.tenant_id == tenant_id,
        OrganizationMember.status == "active"
    ).first()
    
    if member:
        return member.role
    
    # User is not a member - this shouldn't happen normally
    # because tenant_id comes from their JWT, but handle gracefully
    logger.warning(
        f"User {user_id} accessing tenant {tenant_id} but not a member"
    )
    return None


async def get_user_context(
    user_id: str = Depends(get_current_user_id),
    tenant_id: str = Depends(get_current_tenant_id),
    db: Session = Depends(get_db)
) -> UserContext:
    """
    Get full user context including role.
    
    This is useful when you need multiple pieces of user info.
    """
    from avanamy.models.tenant import Tenant
    
    # Check if this is a personal tenant
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    
    if tenant and not tenant.is_organization:
        # Personal tenant - user is always owner
        return UserContext(
            user_id=user_id,
            tenant_id=tenant_id,
            role=Role.OWNER.value,
            member=None
        )
    
    # Organization tenant - look up membership
    member = db.query(OrganizationMember).filter(
        OrganizationMember.user_id == user_id,
        OrganizationMember.tenant_id == tenant_id,
        OrganizationMember.status == "active"
    ).first()
    
    return UserContext(
        user_id=user_id,
        tenant_id=tenant_id,
        role=member.role if member else None,
        member=member
    )


def require_permission(permission: Permission) -> Callable:
    """
    FastAPI dependency that requires a specific permission.
    
    Usage:
        @router.post("/providers")
        async def create_provider(
            _: None = Depends(require_permission(Permission.CREATE_PROVIDER)),
            ...
        ):
            ...
    
    Args:
        permission: Required permission
        
    Returns:
        Dependency function that raises 403 if permission not granted
    """
    async def check_permission(
        user_id: str = Depends(get_current_user_id),
        tenant_id: str = Depends(get_current_tenant_id),
        db: Session = Depends(get_db)
    ) -> None:
        # Get user role directly (same logic as get_user_role function)
        from avanamy.models.tenant import Tenant
        
        # Check if this is a personal tenant
        tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
        
        if tenant and not tenant.is_organization:
            role = Role.OWNER.value
        else:
            # Organization tenant - look up membership
            member = db.query(OrganizationMember).filter(
                OrganizationMember.user_id == user_id,
                OrganizationMember.tenant_id == tenant_id,
                OrganizationMember.status == "active"
            ).first()
            
            role = member.role if member else None
        
        if not role:
            logger.warning(f"User {user_id} has no role in tenant {tenant_id}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have access to this organization"
            )
        
        if not has_permission(role, permission):
            logger.warning(
                f"Permission denied: user={user_id} role={role} "
                f"permission={permission.value} tenant={tenant_id}"
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied. Required permission: {permission.value}"
            )
    
    return check_permission


def require_role(minimum_role: Role) -> Callable:
    """
    FastAPI dependency that requires at least a specific role.
    
    Usage:
        @router.delete("/org/settings")
        async def delete_org(
            _: None = Depends(require_role(Role.OWNER)),
            ...
        ):
            ...
    
    Args:
        minimum_role: Minimum required role
        
    Returns:
        Dependency function that raises 403 if role not sufficient
    """
    async def check_role(
        user_id: str = Depends(get_current_user_id),
        tenant_id: str = Depends(get_current_tenant_id),
        db: Session = Depends(get_db)
    ) -> None:
        # Get user role directly
        from avanamy.models.tenant import Tenant
        
        # Check if this is a personal tenant
        tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
        
        if tenant and not tenant.is_organization:
            role = Role.OWNER.value
        else:
            # Organization tenant - look up membership
            member = db.query(OrganizationMember).filter(
                OrganizationMember.user_id == user_id,
                OrganizationMember.tenant_id == tenant_id,
                OrganizationMember.status == "active"
            ).first()
            
            role = member.role if member else None
        
        if not role:
            logger.warning(f"User {user_id} has no role in tenant {tenant_id}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have access to this organization"
            )
        
        if not is_role_at_least(role, minimum_role):
            logger.warning(
                f"Role check failed: user={user_id} role={role} "
                f"minimum={minimum_role.value} tenant={tenant_id}"
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient privileges: {minimum_role.value} role or higher required"
            )
    
    return check_role


def require_any_permission(*permissions: Permission) -> Callable:
    """
    FastAPI dependency that requires any one of the specified permissions.
    
    Usage:
        @router.post("/trigger-action")
        async def trigger(
            _: None = Depends(require_any_permission(
                Permission.TRIGGER_POLL,
                Permission.TRIGGER_SCAN
            )),
            ...
        ):
            ...
    """
    async def check_any_permission(
        user_id: str = Depends(get_current_user_id),
        tenant_id: str = Depends(get_current_tenant_id),
        db: Session = Depends(get_db)
    ) -> None:
        # Get user role directly
        from avanamy.models.tenant import Tenant
        
        # Check if this is a personal tenant
        tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
        
        if tenant and not tenant.is_organization:
            role = Role.OWNER.value
        else:
            # Organization tenant - look up membership
            member = db.query(OrganizationMember).filter(
                OrganizationMember.user_id == user_id,
                OrganizationMember.tenant_id == tenant_id,
                OrganizationMember.status == "active"
            ).first()
            
            role = member.role if member else None
        
        if not role:
            logger.warning(f"User {user_id} has no role in tenant {tenant_id}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have access to this organization"
            )
        
        if not any(has_permission(role, p) for p in permissions):
            perm_names = [p.value for p in permissions]
            logger.warning(
                f"Permission denied: user={user_id} role={role} "
                f"required_any={perm_names} tenant={tenant_id}"
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied: one of {perm_names} required"
            )
    
    return check_any_permission


# Convenience dependencies for common permission checks
async def require_can_manage_providers(
    _: None = Depends(require_permission(Permission.CREATE_PROVIDER))
) -> None:
    """Require permission to manage providers (create/update/delete)."""
    pass


async def require_can_manage_products(
    _: None = Depends(require_permission(Permission.CREATE_PRODUCT))
) -> None:
    """Require permission to manage products (create/update/delete)."""
    pass


async def require_can_upload_specs(
    _: None = Depends(require_permission(Permission.UPLOAD_SPEC))
) -> None:
    """Require permission to upload API specs."""
    pass


async def require_can_manage_watched_apis(
    _: None = Depends(require_permission(Permission.CREATE_WATCHED_API))
) -> None:
    """Require permission to manage watched APIs."""
    pass


async def require_can_manage_code_repos(
    _: None = Depends(require_permission(Permission.CREATE_CODE_REPO))
) -> None:
    """Require permission to manage code repositories."""
    pass


async def require_can_manage_alerts(
    _: None = Depends(require_permission(Permission.CREATE_ALERT_CONFIG))
) -> None:
    """Require permission to manage alert configurations."""
    pass


async def require_can_manage_members(
    _: None = Depends(require_permission(Permission.INVITE_MEMBER))
) -> None:
    """Require permission to invite/remove members."""
    pass


async def require_owner(
    _: None = Depends(require_role(Role.OWNER))
) -> None:
    """Require owner role."""
    pass


async def require_admin(
    _: None = Depends(require_role(Role.ADMIN))
) -> None:
    """Require admin role or higher."""
    pass


async def require_developer(
    _: None = Depends(require_role(Role.DEVELOPER))
) -> None:
    """Require developer role or higher."""
    pass