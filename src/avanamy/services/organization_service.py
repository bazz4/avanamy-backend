"""
Organization service for managing memberships and invitations.

Handles:
- User membership in organizations
- Invitation creation and acceptance
- Role management
- Member removal
"""
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime, timedelta, timezone
import secrets
import logging

from avanamy.models.tenant import Tenant
from avanamy.models.organization_member import OrganizationMember
from avanamy.models.organization_invitation import OrganizationInvitation

logger = logging.getLogger(__name__)


class OrganizationService:
    """Service for managing organization memberships and invitations."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def get_user_organizations(self, user_id: str) -> List[Tenant]:
        """
        Get all organizations a user belongs to.
        
        Args:
            user_id: Clerk user_id
            
        Returns:
            List of Tenant objects (organizations)
        """
        members = self.db.query(OrganizationMember).filter(
            OrganizationMember.user_id == user_id,
            OrganizationMember.status == "active"
        ).all()
        
        tenant_ids = [m.tenant_id for m in members]
        
        return self.db.query(Tenant).filter(
            Tenant.id.in_(tenant_ids),
            Tenant.status == "active"
        ).all()
    
    def get_organization_members(self, tenant_id: str) -> List[OrganizationMember]:
        """
        Get all active members of an organization.
        
        Args:
            tenant_id: Organization (tenant) ID
            
        Returns:
            List of OrganizationMember objects
        """
        return self.db.query(OrganizationMember).filter(
            OrganizationMember.tenant_id == tenant_id,
            OrganizationMember.status == "active"
        ).order_by(OrganizationMember.joined_at).all()
    
    def get_user_role(self, user_id: str, tenant_id: str) -> Optional[str]:
        """
        Get a user's role in an organization.
        
        Args:
            user_id: Clerk user_id
            tenant_id: Organization (tenant) ID
            
        Returns:
            Role string ('owner', 'admin', 'developer', 'viewer') or None
        """
        member = self.db.query(OrganizationMember).filter(
            OrganizationMember.user_id == user_id,
            OrganizationMember.tenant_id == tenant_id,
            OrganizationMember.status == "active"
        ).first()
        
        return member.role if member else None
    
    def is_member(self, user_id: str, tenant_id: str) -> bool:
        """
        Check if a user is an active member of an organization.
        
        Args:
            user_id: Clerk user_id
            tenant_id: Organization (tenant) ID
            
        Returns:
            True if active member, False otherwise
        """
        return self.get_user_role(user_id, tenant_id) is not None
    
    def invite_user(
        self,
        tenant_id: str,
        email: str,
        role: str,
        invited_by_user_id: str,
        invited_by_name: str
    ) -> OrganizationInvitation:
        """
        Create an invitation for a new user to join the organization.
        
        Args:
            tenant_id: Organization (tenant) ID
            email: Email address of person to invite
            role: Role they'll have ('owner', 'admin', 'developer', 'viewer')
            invited_by_user_id: Clerk user_id of person sending invite
            invited_by_name: Display name of person sending invite
            
        Returns:
            OrganizationInvitation object
            
        Raises:
            ValueError: If user already a member or has pending invitation
        """
        # Check if user is already a member
        existing = self.db.query(OrganizationMember).filter(
            OrganizationMember.tenant_id == tenant_id,
            OrganizationMember.user_email == email,
            OrganizationMember.status == "active"
        ).first()
        
        if existing:
            raise ValueError(f"User {email} is already a member of this organization")
        
        # Check for pending invitation
        pending = self.db.query(OrganizationInvitation).filter(
            OrganizationInvitation.tenant_id == tenant_id,
            OrganizationInvitation.email == email,
            OrganizationInvitation.status == "pending"
        ).first()
        
        if pending:
            raise ValueError(f"User {email} already has a pending invitation")
        
        # Create invitation
        token = secrets.token_urlsafe(32)
        invitation = OrganizationInvitation(
            tenant_id=tenant_id,
            email=email,
            role=role,
            invited_by_user_id=invited_by_user_id,
            invited_by_name=invited_by_name,
            token=token,
            status="pending",
            expires_at=datetime.now(timezone.utc) + timedelta(days=7),
            created_by_user_id=invited_by_user_id
        )
        
        self.db.add(invitation)
        self.db.commit()
        self.db.refresh(invitation)
        
        logger.info(f"Created invitation for {email} to join {tenant_id}")
        return invitation
    
    def get_pending_invitations(self, tenant_id: str) -> List[OrganizationInvitation]:
        """
        Get all pending invitations for an organization.
        
        Args:
            tenant_id: Organization (tenant) ID
            
        Returns:
            List of pending OrganizationInvitation objects
        """
        return self.db.query(OrganizationInvitation).filter(
            OrganizationInvitation.tenant_id == tenant_id,
            OrganizationInvitation.status == "pending"
        ).order_by(OrganizationInvitation.created_at.desc()).all()
    
    def accept_invitation(self, token: str, user_id: str, user_email: str, user_name: str) -> OrganizationMember:
        """
        Accept an invitation and add user to organization.
        
        Args:
            token: Invitation token
            user_id: Clerk user_id of accepting user
            user_email: Email of accepting user
            user_name: Display name of accepting user
            
        Returns:
            OrganizationMember object
            
        Raises:
            ValueError: If token invalid, invitation expired, etc.
        """
        invitation = self.db.query(OrganizationInvitation).filter(
            OrganizationInvitation.token == token
        ).first()
        
        if not invitation:
            raise ValueError("Invalid invitation token")
        
        if invitation.status != "pending":
            raise ValueError(f"Invitation already {invitation.status}")
        
        if invitation.is_expired:
            invitation.status = "expired"
            self.db.commit()
            raise ValueError("Invitation has expired")
        
        # Verify email matches (optional - can be strict or lenient)
        # if invitation.email.lower() != user_email.lower():
        #     raise ValueError("Email does not match invitation")
        
        # Create member
        member = OrganizationMember(
            tenant_id=invitation.tenant_id,
            user_id=user_id,
            role=invitation.role,
            status="active",
            user_email=user_email,
            user_name=user_name,
            invited_by_user_id=invitation.invited_by_user_id,
            invited_at=invitation.created_at,
            joined_at=datetime.now(timezone.utc),
            created_by_user_id=user_id
        )
        
        self.db.add(member)
        
        # Mark invitation as accepted
        invitation.status = "accepted"
        invitation.accepted_at = datetime.now(timezone.utc)
        
        self.db.commit()
        self.db.refresh(member)
        
        logger.info(f"User {user_id} accepted invitation to join {invitation.tenant_id}")
        return member
    
    def remove_member(self, tenant_id: str, user_id: str, removed_by_user_id: str):
        """
        Remove a user from an organization.
        
        Args:
            tenant_id: Organization (tenant) ID
            user_id: Clerk user_id of member to remove
            removed_by_user_id: Clerk user_id of person doing the removal
            
        Raises:
            ValueError: If user not a member or trying to remove owner
        """
        member = self.db.query(OrganizationMember).filter(
            OrganizationMember.tenant_id == tenant_id,
            OrganizationMember.user_id == user_id,
            OrganizationMember.status == "active"
        ).first()
        
        if not member:
            raise ValueError(f"User {user_id} is not a member of this organization")
        
        # Can't remove the owner
        if member.role == "owner":
            raise ValueError("Cannot remove the organization owner")
        
        member.status = "removed"
        member.updated_by_user_id = removed_by_user_id
        
        self.db.commit()
        logger.info(f"Removed user {user_id} from {tenant_id}")
    
    def update_member_role(
        self,
        tenant_id: str,
        user_id: str,
        new_role: str,
        updated_by_user_id: str
    ):
        """
        Update a user's role in an organization.
        
        Args:
            tenant_id: Organization (tenant) ID
            user_id: Clerk user_id of member
            new_role: New role ('owner', 'admin', 'developer', 'viewer')
            updated_by_user_id: Clerk user_id of person making the change
            
        Raises:
            ValueError: If user not a member or trying to change owner role
        """
        member = self.db.query(OrganizationMember).filter(
            OrganizationMember.tenant_id == tenant_id,
            OrganizationMember.user_id == user_id,
            OrganizationMember.status == "active"
        ).first()
        
        if not member:
            raise ValueError(f"User {user_id} is not a member of this organization")
        
        # Can't change owner role (would need ownership transfer flow)
        if member.role == "owner":
            raise ValueError("Cannot change owner role. Use ownership transfer instead.")
        
        member.role = new_role
        member.updated_by_user_id = updated_by_user_id
        
        self.db.commit()
        logger.info(f"Updated role for {user_id} in {tenant_id} to {new_role}")
    
    def revoke_invitation(self, invitation_id: str, revoked_by_user_id: str):
        """
        Revoke a pending invitation.
        
        Args:
            invitation_id: UUID of invitation
            revoked_by_user_id: Clerk user_id of person revoking
            
        Raises:
            ValueError: If invitation not found or not pending
        """
        invitation = self.db.query(OrganizationInvitation).filter(
            OrganizationInvitation.id == invitation_id
        ).first()
        
        if not invitation:
            raise ValueError("Invitation not found")
        
        if invitation.status != "pending":
            raise ValueError(f"Cannot revoke invitation with status: {invitation.status}")
        
        invitation.status = "revoked"
        invitation.updated_by_user_id = revoked_by_user_id
        
        self.db.commit()
        logger.info(f"Revoked invitation {invitation_id}")
