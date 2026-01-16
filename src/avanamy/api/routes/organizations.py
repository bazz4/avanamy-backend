"""
API routes for organization management.

Endpoints:
- GET /organizations/current/members - List organization members
- POST /organizations/current/invitations - Invite a user
- GET /organizations/current/invitations - List pending invitations
- POST /organizations/invitations/{token}/accept - Accept invitation
- DELETE /organizations/current/members/{user_id} - Remove member
- PATCH /organizations/current/members/{user_id}/role - Update member role
- DELETE /organizations/current/invitations/{invitation_id} - Revoke invitation
"""
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session
from typing import List, Optional
from uuid import UUID
from datetime import datetime

from avanamy.auth.clerk import get_current_user_id, get_current_tenant_id
from avanamy.db.database import get_db
from avanamy.services.organization_service import OrganizationService
from avanamy.services.email_service import EmailService
from avanamy.models.organization_member import OrganizationMember
from avanamy.models.organization_invitation import OrganizationInvitation
from avanamy.models.tenant import Tenant

router = APIRouter(prefix="/organizations", tags=["organizations"])


# ==================== Request/Response Models ====================

class InviteUserRequest(BaseModel):
    """Request to invite a user to the organization."""
    email: EmailStr
    role: str = "member"
    
    class Config:
        json_schema_extra = {
            "example": {
                "email": "colleague@company.com",
                "role": "developer"
            }
        }


class UpdateMemberRoleRequest(BaseModel):
    """Request to update a member's role."""
    role: str
    
    class Config:
        json_schema_extra = {
            "example": {
                "role": "admin"
            }
        }


class OrganizationMemberResponse(BaseModel):
    """Response model for organization member."""
    id: UUID
    user_id: str
    role: str
    status: str
    user_email: Optional[str]
    user_name: Optional[str]
    joined_at: Optional[datetime]
    invited_by_user_id: Optional[str]
    
    class Config:
        from_attributes = True


class OrganizationInvitationResponse(BaseModel):
    """Response model for organization invitation."""
    id: UUID
    email: str
    role: str
    status: str
    invited_by_name: Optional[str]
    expires_at: datetime
    created_at: datetime
    
    class Config:
        from_attributes = True


# ==================== Endpoints ====================

@router.get("/current/members", response_model=List[OrganizationMemberResponse])
def list_organization_members(
    tenant_id: str = Depends(get_current_tenant_id),
    db: Session = Depends(get_db)
):
    """
    List all members of the current organization.
    
    Returns members with their roles, status, and join dates.
    """
    service = OrganizationService(db)
    members = service.get_organization_members(tenant_id)
    return members


@router.post("/current/invitations", response_model=OrganizationInvitationResponse, status_code=status.HTTP_201_CREATED)
async def invite_user_to_organization(
    request: InviteUserRequest,
    background_tasks: BackgroundTasks,
    user_id: str = Depends(get_current_user_id),
    tenant_id: str = Depends(get_current_tenant_id),
    db: Session = Depends(get_db)
):
    """
    Invite a user to join the current organization.
    
    Only owners and admins can invite users.
    Invitation expires after 7 days.
    """
    service = OrganizationService(db)
    
    # Check if current user has permission to invite
    user_role = service.get_user_role(user_id, tenant_id)
    if user_role not in ["owner", "admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only owners and admins can invite users"
        )
    
    # Get inviter name from Clerk (optional, fallback to email)
    try:
        from clerk_backend_api import Clerk
        import os
        clerk = Clerk(bearer_auth=os.getenv("CLERK_SECRET_KEY"))
        user = clerk.users.get(user_id=user_id)
        inviter_name = f"{user.first_name or ''} {user.last_name or ''}".strip()
        if not inviter_name:
            inviter_name = user.email_addresses[0].email_address if user.email_addresses else "Team member"
    except Exception as e:
        inviter_name = "Team member"
    
    try:
        invitation = service.invite_user(
            tenant_id=tenant_id,
            email=request.email,
            role=request.role,
            invited_by_user_id=user_id,
            invited_by_name=inviter_name
        )
        
        tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
        organization_name = tenant.name if tenant else tenant_id

        email_service = EmailService()
        background_tasks.add_task(
            email_service.send_invitation_email,
            to_email=invitation.email,
            inviter_name=inviter_name,
            organization_name=organization_name,
            invitation_token=invitation.token
        )
        
        return invitation
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get("/current/invitations", response_model=List[OrganizationInvitationResponse])
def list_pending_invitations(
    user_id: str = Depends(get_current_user_id),
    tenant_id: str = Depends(get_current_tenant_id),
    db: Session = Depends(get_db)
):
    """
    List pending invitations for the current organization.
    
    Only owners and admins can view invitations.
    """
    service = OrganizationService(db)
    
    # Check permission
    user_role = service.get_user_role(user_id, tenant_id)
    if user_role not in ["owner", "admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only owners and admins can view invitations"
        )
    
    invitations = service.get_pending_invitations(tenant_id)
    return invitations


@router.post("/invitations/{token}/accept", response_model=OrganizationMemberResponse)
async def accept_organization_invitation(
    token: str,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """
    Accept an invitation to join an organization.
    
    The token is provided in the invitation email.
    User must be authenticated to accept.
    """
    # Get user info from Clerk
    try:
        from clerk_backend_api import Clerk
        import os
        clerk = Clerk(bearer_auth=os.getenv("CLERK_SECRET_KEY"))
        user = clerk.users.get(user_id=user_id)
        user_email = user.email_addresses[0].email_address if user.email_addresses else "unknown"
        user_name = f"{user.first_name or ''} {user.last_name or ''}".strip() or user_email
    except Exception as e:
        # Fallback if Clerk fails
        user_email = "unknown"
        user_name = "User"
    
    service = OrganizationService(db)
    
    try:
        member = service.accept_invitation(token, user_id, user_email, user_name)
        return member
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.delete("/current/members/{member_user_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_organization_member(
    member_user_id: str,
    user_id: str = Depends(get_current_user_id),
    tenant_id: str = Depends(get_current_tenant_id),
    db: Session = Depends(get_db)
):
    """
    Remove a member from the current organization.
    
    Only owners and admins can remove members.
    Cannot remove the owner.
    """
    service = OrganizationService(db)
    
    # Check permission
    user_role = service.get_user_role(user_id, tenant_id)
    if user_role not in ["owner", "admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only owners and admins can remove members"
        )
    
    try:
        service.remove_member(tenant_id, member_user_id, user_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.patch("/current/members/{member_user_id}/role", status_code=status.HTTP_200_OK)
def update_member_role(
    member_user_id: str,
    request: UpdateMemberRoleRequest,
    user_id: str = Depends(get_current_user_id),
    tenant_id: str = Depends(get_current_tenant_id),
    db: Session = Depends(get_db)
):
    """
    Update a member's role in the organization.
    
    Only owners can change roles.
    Cannot change the owner's role.
    """
    service = OrganizationService(db)
    
    # Check permission - only owners can change roles
    user_role = service.get_user_role(user_id, tenant_id)
    if user_role != "owner":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only owners can change member roles"
        )
    
    try:
        service.update_member_role(tenant_id, member_user_id, request.role, user_id)
        return {"status": "success", "message": f"Role updated to {request.role}"}
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.delete("/current/invitations/{invitation_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_invitation(
    invitation_id: UUID,
    user_id: str = Depends(get_current_user_id),
    tenant_id: str = Depends(get_current_tenant_id),
    db: Session = Depends(get_db)
):
    """
    Revoke a pending invitation.
    
    Only owners and admins can revoke invitations.
    """
    service = OrganizationService(db)
    
    # Check permission
    user_role = service.get_user_role(user_id, tenant_id)
    if user_role not in ["owner", "admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only owners and admins can revoke invitations"
        )
    
    # Verify invitation belongs to this org
    invitation = db.query(OrganizationInvitation).filter(
        OrganizationInvitation.id == invitation_id,
        OrganizationInvitation.tenant_id == tenant_id
    ).first()
    
    if not invitation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invitation not found"
        )
    
    try:
        service.revoke_invitation(str(invitation_id), user_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
