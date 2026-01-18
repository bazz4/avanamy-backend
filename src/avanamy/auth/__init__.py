"""
Authentication and Authorization module for Avanamy.

This module provides:
- Clerk JWT authentication (clerk.py)
- Permission definitions (permissions.py)
- RBAC middleware for FastAPI (rbac.py)

Usage:
    from avanamy.auth import (
        # Authentication
        get_current_user_id,
        get_current_tenant_id,
        
        # Permissions
        Permission,
        Role,
        has_permission,
        
        # RBAC middleware
        require_permission,
        require_role,
        get_user_context,
    )
"""

# Re-export from clerk.py
from avanamy.auth.clerk import (
    get_current_user_id,
    get_current_tenant_id,
)

# Re-export from permissions.py
from avanamy.auth.permissions import (
    Permission,
    Role,
    has_permission,
    has_any_permission,
    has_all_permissions,
    get_role_permissions,
    is_role_at_least,
    can_manage_providers,
    can_manage_products,
    can_upload_specs,
    can_manage_watched_apis,
    can_manage_code_repos,
    can_manage_alerts,
    can_manage_members,
    can_change_roles,
)

# Re-export from rbac.py
from avanamy.auth.rbac import (
    UserContext,
    get_user_role,
    get_user_context,
    require_permission,
    require_role,
    require_any_permission,
    require_can_manage_providers,
    require_can_manage_products,
    require_can_upload_specs,
    require_can_manage_watched_apis,
    require_can_manage_code_repos,
    require_can_manage_alerts,
    require_can_manage_members,
    require_owner,
    require_admin,
    require_developer,
)

__all__ = [
    # Authentication
    "get_current_user_id",
    "get_current_tenant_id",
    
    # Permissions
    "Permission",
    "Role",
    "has_permission",
    "has_any_permission",
    "has_all_permissions",
    "get_role_permissions",
    "is_role_at_least",
    "can_manage_providers",
    "can_manage_products",
    "can_upload_specs",
    "can_manage_watched_apis",
    "can_manage_code_repos",
    "can_manage_alerts",
    "can_manage_members",
    "can_change_roles",
    
    # RBAC
    "UserContext",
    "get_user_role",
    "get_user_context",
    "require_permission",
    "require_role",
    "require_any_permission",
    "require_can_manage_providers",
    "require_can_manage_products",
    "require_can_upload_specs",
    "require_can_manage_watched_apis",
    "require_can_manage_code_repos",
    "require_can_manage_alerts",
    "require_can_manage_members",
    "require_owner",
    "require_admin",
    "require_developer",
]