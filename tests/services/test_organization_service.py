import pytest
import uuid
from datetime import datetime, timedelta, timezone

from avanamy.services.organization_service import OrganizationService
from avanamy.models.organization_invitation import OrganizationInvitation
from avanamy.models.organization_member import OrganizationMember


def _create_member(db, tenant_id="tenant-1", user_id="user-1", role="member", status="active"):
    member = OrganizationMember(
        tenant_id=tenant_id,
        user_id=user_id,
        role=role,
        status=status,
        user_email="user@example.com",
        user_name="User One",
        created_by_user_id="creator"
    )
    db.add(member)
    db.commit()
    db.refresh(member)
    return member


def _create_invitation(
    db,
    tenant_id="tenant-1",
    email="invitee@example.com",
    role="member",
    status="pending",
    token="token-123",
    expires_at=None
):
    invitation = OrganizationInvitation(
        tenant_id=tenant_id,
        email=email,
        role=role,
        invited_by_user_id="inviter-1",
        invited_by_name="Inviter One",
        token=token,
        status=status,
        expires_at=expires_at or (datetime.now(timezone.utc) + timedelta(days=7)),
        created_by_user_id="inviter-1"
    )
    db.add(invitation)
    db.commit()
    db.refresh(invitation)
    return invitation


def test_invite_user_creates_invitation(db):
    service = OrganizationService(db)
    before = datetime.now(timezone.utc)

    invitation = service.invite_user(
        tenant_id="tenant-1",
        email="newuser@example.com",
        role="developer",
        invited_by_user_id="inviter-1",
        invited_by_name="Inviter One"
    )

    assert invitation.email == "newuser@example.com"
    assert invitation.role == "developer"
    assert invitation.status == "pending"
    assert invitation.token
    compare_base = before.replace(tzinfo=None) if invitation.expires_at.tzinfo is None else before
    assert invitation.expires_at > compare_base
    assert invitation.expires_at < compare_base + timedelta(days=8)


def test_invite_user_rejects_existing_member(db):
    _create_member(db, tenant_id="tenant-1", user_id="user-1", role="member")
    service = OrganizationService(db)

    with pytest.raises(ValueError, match="already a member"):
        service.invite_user(
            tenant_id="tenant-1",
            email="user@example.com",
            role="member",
            invited_by_user_id="inviter-1",
            invited_by_name="Inviter One"
        )


def test_invite_user_rejects_pending_invitation(db):
    _create_invitation(db, tenant_id="tenant-1", email="invitee@example.com")
    service = OrganizationService(db)

    with pytest.raises(ValueError, match="pending invitation"):
        service.invite_user(
            tenant_id="tenant-1",
            email="invitee@example.com",
            role="member",
            invited_by_user_id="inviter-1",
            invited_by_name="Inviter One"
        )


def test_accept_invitation_invalid_token(db):
    service = OrganizationService(db)

    with pytest.raises(ValueError, match="Invalid invitation token"):
        service.accept_invitation("missing-token", "user-2", "user2@example.com", "User Two")


def test_accept_invitation_expired_marks_expired(db):
    invitation = _create_invitation(
        db,
        token="expired-token",
        expires_at=datetime.now(timezone.utc) - timedelta(days=1)
    )
    service = OrganizationService(db)

    with pytest.raises(ValueError, match="expired"):
        service.accept_invitation(invitation.token, "user-2", "user2@example.com", "User Two")

    refreshed = db.query(OrganizationInvitation).filter_by(id=invitation.id).first()
    assert refreshed.status == "expired"


def test_accept_invitation_creates_member_and_updates_status(db):
    invitation = _create_invitation(db, token="valid-token")
    service = OrganizationService(db)

    member = service.accept_invitation(invitation.token, "user-2", "user2@example.com", "User Two")

    assert member.user_id == "user-2"
    assert member.tenant_id == invitation.tenant_id
    assert member.role == invitation.role
    assert member.status == "active"

    refreshed = db.query(OrganizationInvitation).filter_by(id=invitation.id).first()
    assert refreshed.status == "accepted"
    assert refreshed.accepted_at is not None


def test_remove_member_rejects_missing_member(db):
    service = OrganizationService(db)

    with pytest.raises(ValueError, match="not a member"):
        service.remove_member("tenant-1", "user-1", "remover-1")


def test_remove_member_rejects_owner(db):
    _create_member(db, tenant_id="tenant-1", user_id="owner-1", role="owner")
    service = OrganizationService(db)

    with pytest.raises(ValueError, match="Cannot remove the organization owner"):
        service.remove_member("tenant-1", "owner-1", "remover-1")


def test_remove_member_marks_removed(db):
    member = _create_member(db, tenant_id="tenant-1", user_id="user-1", role="admin")
    service = OrganizationService(db)

    service.remove_member("tenant-1", "user-1", "remover-1")

    refreshed = db.query(OrganizationMember).filter_by(id=member.id).first()
    assert refreshed.status == "removed"


def test_update_member_role_rejects_missing_member(db):
    service = OrganizationService(db)

    with pytest.raises(ValueError, match="not a member"):
        service.update_member_role("tenant-1", "user-1", "viewer", "updater-1")


def test_update_member_role_rejects_owner(db):
    _create_member(db, tenant_id="tenant-1", user_id="owner-1", role="owner")
    service = OrganizationService(db)

    with pytest.raises(ValueError, match="Cannot change owner role"):
        service.update_member_role("tenant-1", "owner-1", "admin", "updater-1")


def test_update_member_role_updates_role(db):
    member = _create_member(db, tenant_id="tenant-1", user_id="user-1", role="viewer")
    service = OrganizationService(db)

    service.update_member_role("tenant-1", "user-1", "admin", "updater-1")

    refreshed = db.query(OrganizationMember).filter_by(id=member.id).first()
    assert refreshed.role == "admin"


def test_revoke_invitation_missing(db):
    service = OrganizationService(db)

    with pytest.raises(ValueError, match="Invitation not found"):
        service.revoke_invitation(uuid.uuid4(), "revoker-1")


def test_revoke_invitation_rejects_non_pending(db):
    invitation = _create_invitation(db, status="accepted")
    service = OrganizationService(db)

    with pytest.raises(ValueError, match="Cannot revoke invitation"):
        service.revoke_invitation(invitation.id, "revoker-1")


def test_revoke_invitation_marks_revoked(db):
    invitation = _create_invitation(db, status="pending")
    service = OrganizationService(db)

    service.revoke_invitation(invitation.id, "revoker-1")

    refreshed = db.query(OrganizationInvitation).filter_by(id=invitation.id).first()
    assert refreshed.status == "revoked"
    assert refreshed.updated_by_user_id == "revoker-1"
