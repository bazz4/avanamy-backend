"""
OrganizationMember model - tracks which users belong to which organizations.

This is the junction table between Clerk users and our tenants (organizations).
"""
from sqlalchemy import Column, String, DateTime, Index
from sqlalchemy.dialects.postgresql import UUID, ENUM
from sqlalchemy.orm import relationship
from uuid import uuid4
import enum

from avanamy.db.database import Base
from avanamy.models.mixins import AuditMixin


class MemberRole(str, enum.Enum):
    """User roles within an organization."""
    OWNER = "owner"
    ADMIN = "admin"
    DEVELOPER = "developer"
    VIEWER = "viewer"


class OrganizationMember(Base, AuditMixin):
    """
    Tracks user membership in organizations (tenants).
    
    Each record represents one user's membership in one organization.
    Stores role, status, and invitation tracking.
    """
    __tablename__ = "organization_members"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4, nullable=False)
    
    # The organization (which is a tenant)
    tenant_id = Column(String(255), nullable=False, index=True)
    
    # The Clerk user_id
    user_id = Column(String(255), nullable=False, index=True)
    
    # User's role in this organization (Phase 4A: Now using enum)
    role = Column(
        ENUM('owner', 'admin', 'developer', 'viewer', name='member_role_enum', create_type=False),
        nullable=False,
        default='developer',
        server_default='developer'
    )
    
    # Membership status
    status = Column(String(50), nullable=False, default="active")
    # Status: 'active', 'pending', 'suspended', 'removed'
    
    # Cached user info from Clerk (for performance, display purposes)
    user_email = Column(String, nullable=True)
    user_name = Column(String, nullable=True)
    
    # Invitation tracking
    invited_by_user_id = Column(String(255), nullable=True)
    invited_at = Column(DateTime(timezone=True), nullable=True)
    joined_at = Column(DateTime(timezone=True), nullable=True)
    
    __table_args__ = (
        # Unique constraint: one user can only be a member once per org
        Index("ix_org_members_tenant_user", "tenant_id", "user_id", unique=True),
        Index("ix_org_members_status", "status"),
    )
    
    def __repr__(self):
        return f"<OrganizationMember(user={self.user_id}, tenant={self.tenant_id}, role={self.role})>"