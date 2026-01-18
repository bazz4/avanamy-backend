"""
Permission definitions and role-based access control.

This module defines:
- All permissions in the system
- Role -> Permission mappings
- Helper functions to check permissions

Roles (highest to lowest privilege):
- owner: Full access, can transfer ownership, manage billing
- admin: Full operational access, can invite/remove members
- developer: Can upload specs, trigger scans, manage watched APIs
- viewer: Read-only access to all data
"""
from enum import Enum
from typing import Set


class Permission(str, Enum):
    """All permissions in the Avanamy system."""
    
    # Read permissions (all roles have these)
    READ_PROVIDERS = "read:providers"
    READ_PRODUCTS = "read:products"
    READ_SPECS = "read:specs"
    READ_VERSIONS = "read:versions"
    READ_WATCHED_APIS = "read:watched_apis"
    READ_CODE_REPOS = "read:code_repos"
    READ_IMPACT_ANALYSIS = "read:impact_analysis"
    READ_ALERT_CONFIGS = "read:alert_configs"
    READ_ALERT_HISTORY = "read:alert_history"
    READ_MEMBERS = "read:members"
    READ_INVITATIONS = "read:invitations"
    READ_DOCS = "read:docs"
    
    # Provider/Product management (admin+)
    CREATE_PROVIDER = "create:provider"
    UPDATE_PROVIDER = "update:provider"
    DELETE_PROVIDER = "delete:provider"
    CREATE_PRODUCT = "create:product"
    UPDATE_PRODUCT = "update:product"
    DELETE_PRODUCT = "delete:product"
    
    # Spec management (developer+)
    UPLOAD_SPEC = "upload:spec"
    UPDATE_SPEC = "update:spec"
    REGENERATE_DOCS = "regenerate:docs"
    
    # Watched API management (developer+)
    CREATE_WATCHED_API = "create:watched_api"
    UPDATE_WATCHED_API = "update:watched_api"
    DELETE_WATCHED_API = "delete:watched_api"
    TRIGGER_POLL = "trigger:poll"
    
    # Code repository management (developer+)
    CREATE_CODE_REPO = "create:code_repo"
    UPDATE_CODE_REPO = "update:code_repo"
    DELETE_CODE_REPO = "delete:code_repo"
    TRIGGER_SCAN = "trigger:scan"
    
    # Alert configuration (admin+)
    CREATE_ALERT_CONFIG = "create:alert_config"
    UPDATE_ALERT_CONFIG = "update:alert_config"
    DELETE_ALERT_CONFIG = "delete:alert_config"
    
    # Member management (admin+)
    INVITE_MEMBER = "invite:member"
    REMOVE_MEMBER = "remove:member"
    
    # Role management (owner only)
    CHANGE_MEMBER_ROLE = "change:member_role"
    
    # Organization management (owner only)
    MANAGE_ORG_SETTINGS = "manage:org_settings"
    TRANSFER_OWNERSHIP = "transfer:ownership"


class Role(str, Enum):
    """User roles in order of privilege (highest first)."""
    OWNER = "owner"
    ADMIN = "admin"
    DEVELOPER = "developer"
    VIEWER = "viewer"


# Role hierarchy for comparison
ROLE_HIERARCHY = {
    Role.OWNER: 4,
    Role.ADMIN: 3,
    Role.DEVELOPER: 2,
    Role.VIEWER: 1,
}


# Define which permissions each role has
ROLE_PERMISSIONS: dict[Role, Set[Permission]] = {
    Role.VIEWER: {
        # Viewers can read everything
        Permission.READ_PROVIDERS,
        Permission.READ_PRODUCTS,
        Permission.READ_SPECS,
        Permission.READ_VERSIONS,
        Permission.READ_WATCHED_APIS,
        Permission.READ_CODE_REPOS,
        Permission.READ_IMPACT_ANALYSIS,
        Permission.READ_ALERT_CONFIGS,
        Permission.READ_ALERT_HISTORY,
        Permission.READ_MEMBERS,
        Permission.READ_DOCS,
    },
    
    Role.DEVELOPER: {
        # Developers inherit all viewer permissions
        Permission.READ_PROVIDERS,
        Permission.READ_PRODUCTS,
        Permission.READ_SPECS,
        Permission.READ_VERSIONS,
        Permission.READ_WATCHED_APIS,
        Permission.READ_CODE_REPOS,
        Permission.READ_IMPACT_ANALYSIS,
        Permission.READ_ALERT_CONFIGS,
        Permission.READ_ALERT_HISTORY,
        Permission.READ_MEMBERS,
        Permission.READ_DOCS,
        
        # Plus spec management
        Permission.UPLOAD_SPEC,
        Permission.UPDATE_SPEC,
        Permission.REGENERATE_DOCS,
        
        # Plus watched API management
        Permission.CREATE_WATCHED_API,
        Permission.UPDATE_WATCHED_API,
        Permission.DELETE_WATCHED_API,
        Permission.TRIGGER_POLL,
        
        # Plus code repo management
        Permission.CREATE_CODE_REPO,
        Permission.UPDATE_CODE_REPO,
        Permission.DELETE_CODE_REPO,
        Permission.TRIGGER_SCAN,
    },
    
    Role.ADMIN: {
        # Admins inherit all developer permissions
        Permission.READ_PROVIDERS,
        Permission.READ_PRODUCTS,
        Permission.READ_SPECS,
        Permission.READ_VERSIONS,
        Permission.READ_WATCHED_APIS,
        Permission.READ_CODE_REPOS,
        Permission.READ_IMPACT_ANALYSIS,
        Permission.READ_ALERT_CONFIGS,
        Permission.READ_ALERT_HISTORY,
        Permission.READ_MEMBERS,
        Permission.READ_INVITATIONS,  # Admins can see invitations
        Permission.READ_DOCS,
        Permission.UPLOAD_SPEC,
        Permission.UPDATE_SPEC,
        Permission.REGENERATE_DOCS,
        Permission.CREATE_WATCHED_API,
        Permission.UPDATE_WATCHED_API,
        Permission.DELETE_WATCHED_API,
        Permission.TRIGGER_POLL,
        Permission.CREATE_CODE_REPO,
        Permission.UPDATE_CODE_REPO,
        Permission.DELETE_CODE_REPO,
        Permission.TRIGGER_SCAN,
        
        # Plus provider/product management
        Permission.CREATE_PROVIDER,
        Permission.UPDATE_PROVIDER,
        Permission.DELETE_PROVIDER,
        Permission.CREATE_PRODUCT,
        Permission.UPDATE_PRODUCT,
        Permission.DELETE_PRODUCT,
        
        # Plus alert configuration
        Permission.CREATE_ALERT_CONFIG,
        Permission.UPDATE_ALERT_CONFIG,
        Permission.DELETE_ALERT_CONFIG,
        
        # Plus member management
        Permission.INVITE_MEMBER,
        Permission.REMOVE_MEMBER,
    },
    
    Role.OWNER: {
        # Owners have ALL permissions
        Permission.READ_PROVIDERS,
        Permission.READ_PRODUCTS,
        Permission.READ_SPECS,
        Permission.READ_VERSIONS,
        Permission.READ_WATCHED_APIS,
        Permission.READ_CODE_REPOS,
        Permission.READ_IMPACT_ANALYSIS,
        Permission.READ_ALERT_CONFIGS,
        Permission.READ_ALERT_HISTORY,
        Permission.READ_MEMBERS,
        Permission.READ_INVITATIONS,
        Permission.READ_DOCS,
        Permission.UPLOAD_SPEC,
        Permission.UPDATE_SPEC,
        Permission.REGENERATE_DOCS,
        Permission.CREATE_WATCHED_API,
        Permission.UPDATE_WATCHED_API,
        Permission.DELETE_WATCHED_API,
        Permission.TRIGGER_POLL,
        Permission.CREATE_CODE_REPO,
        Permission.UPDATE_CODE_REPO,
        Permission.DELETE_CODE_REPO,
        Permission.TRIGGER_SCAN,
        Permission.CREATE_PROVIDER,
        Permission.UPDATE_PROVIDER,
        Permission.DELETE_PROVIDER,
        Permission.CREATE_PRODUCT,
        Permission.UPDATE_PRODUCT,
        Permission.DELETE_PRODUCT,
        Permission.CREATE_ALERT_CONFIG,
        Permission.UPDATE_ALERT_CONFIG,
        Permission.DELETE_ALERT_CONFIG,
        Permission.INVITE_MEMBER,
        Permission.REMOVE_MEMBER,
        
        # Plus owner-only permissions
        Permission.CHANGE_MEMBER_ROLE,
        Permission.MANAGE_ORG_SETTINGS,
        Permission.TRANSFER_OWNERSHIP,
    },
}


def has_permission(role: str | Role | None, permission: Permission) -> bool:
    """
    Check if a role has a specific permission.
    
    Args:
        role: User's role (string or Role enum)
        permission: Permission to check
        
    Returns:
        True if role has the permission, False otherwise
    """
    if role is None:
        return False
    
    # Convert string to Role enum if needed
    if isinstance(role, str):
        try:
            role = Role(role)
        except ValueError:
            # Unknown role has no permissions
            return False
    
    return permission in ROLE_PERMISSIONS.get(role, set())


def has_any_permission(role: str | Role | None, permissions: list[Permission]) -> bool:
    """
    Check if a role has any of the specified permissions.
    
    Args:
        role: User's role
        permissions: List of permissions to check
        
    Returns:
        True if role has at least one permission
    """
    return any(has_permission(role, p) for p in permissions)


def has_all_permissions(role: str | Role | None, permissions: list[Permission]) -> bool:
    """
    Check if a role has all of the specified permissions.
    
    Args:
        role: User's role
        permissions: List of permissions to check
        
    Returns:
        True if role has all permissions
    """
    return all(has_permission(role, p) for p in permissions)


def get_role_permissions(role: str | Role | None) -> Set[Permission]:
    """
    Get all permissions for a role.
    
    Args:
        role: User's role
        
    Returns:
        Set of permissions the role has
    """
    if role is None:
        return set()
    
    if isinstance(role, str):
        try:
            role = Role(role)
        except ValueError:
            return set()
    
    return ROLE_PERMISSIONS.get(role, set())


def is_role_at_least(role: str | Role | None, minimum_role: Role) -> bool:
    """
    Check if a role is at least as privileged as the minimum role.
    
    Args:
        role: User's role
        minimum_role: Minimum required role
        
    Returns:
        True if role meets or exceeds minimum
    """
    if role is None:
        return False
    
    if isinstance(role, str):
        try:
            role = Role(role)
        except ValueError:
            return False
    
    return ROLE_HIERARCHY.get(role, 0) >= ROLE_HIERARCHY.get(minimum_role, 0)


# Convenience functions for common checks
def can_manage_providers(role: str | Role | None) -> bool:
    """Check if role can create/update/delete providers."""
    return has_permission(role, Permission.CREATE_PROVIDER)


def can_manage_products(role: str | Role | None) -> bool:
    """Check if role can create/update/delete products."""
    return has_permission(role, Permission.CREATE_PRODUCT)


def can_upload_specs(role: str | Role | None) -> bool:
    """Check if role can upload API specs."""
    return has_permission(role, Permission.UPLOAD_SPEC)


def can_manage_watched_apis(role: str | Role | None) -> bool:
    """Check if role can manage watched APIs."""
    return has_permission(role, Permission.CREATE_WATCHED_API)


def can_manage_code_repos(role: str | Role | None) -> bool:
    """Check if role can manage code repositories."""
    return has_permission(role, Permission.CREATE_CODE_REPO)


def can_manage_alerts(role: str | Role | None) -> bool:
    """Check if role can manage alert configurations."""
    return has_permission(role, Permission.CREATE_ALERT_CONFIG)


def can_manage_members(role: str | Role | None) -> bool:
    """Check if role can invite/remove members."""
    return has_permission(role, Permission.INVITE_MEMBER)


def can_change_roles(role: str | Role | None) -> bool:
    """Check if role can change member roles."""
    return has_permission(role, Permission.CHANGE_MEMBER_ROLE)