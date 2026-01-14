"""
OrganizationInvitation model - tracks pending invitations to join organizations.

Invitations are sent via email, expire after 7 days, and can only be used once.
"""
from sqlalchemy import Column, String, DateTime, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from uuid import uuid4
from datetime import datetime

from avanamy.db.database import Base
from avanamy.models.mixins import AuditMixin


class OrganizationInvitation(Base, AuditMixin):
    """
    Pending invitation to join an organization.
    
    Created when an admin/owner invites someone via email.
    Expires after 7 days, can be accepted once.
    """
    __tablename__ = "organization_invitations"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4, nullable=False)
    
    # Which organization they're being invited to
    tenant_id = Column(String(255), nullable=False, index=True)
    
    # Email address of invitee
    email = Column(String, nullable=False, index=True)
    
    # Role they'll have when they join
    role = Column(String(50), nullable=False, default="member")
    
    # Who sent the invitation
    invited_by_user_id = Column(String(255), nullable=False)
    invited_by_name = Column(String, nullable=True)
    
    # Secure token for accepting invitation
    token = Column(String(255), nullable=False, unique=True, index=True)
    
    # Invitation status
    status = Column(String(50), nullable=False, default="pending")
    # Status: 'pending', 'accepted', 'expired', 'revoked'
    
    # Expiration tracking
    expires_at = Column(DateTime(timezone=True), nullable=False)
    accepted_at = Column(DateTime(timezone=True), nullable=True)
    
    __table_args__ = (
        Index("ix_org_invitations_email_status", "email", "status"),
        Index("ix_org_invitations_tenant_status", "tenant_id", "status"),
    )
    
    @property
    def is_expired(self) -> bool:
        """Check if invitation has expired."""
        return datetime.utcnow() > self.expires_at
    
    def __repr__(self):
        return f"<OrganizationInvitation(email={self.email}, tenant={self.tenant_id}, status={self.status})>"