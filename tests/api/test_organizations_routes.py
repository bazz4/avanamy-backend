from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from avanamy.main import app
from avanamy.db.database import get_db
from avanamy.auth.clerk import get_current_user_id, get_current_tenant_id
from avanamy.models.tenant import Tenant
from avanamy.models.organization_member import OrganizationMember
from avanamy.models.organization_invitation import OrganizationInvitation
from avanamy.services.email_service import EmailService


def _create_tenant(db, tenant_id="tenant-1", name="Test Org"):
    tenant = Tenant(
        id=tenant_id,
        name=name,
        slug=name.lower().replace(" ", "-"),
        is_organization=True,
        status="active"
    )
    db.add(tenant)
    db.commit()
    db.refresh(tenant)
    return tenant


def _create_member(db, tenant_id="tenant-1", user_id="user-1", role="member"):
    member = OrganizationMember(
        tenant_id=tenant_id,
        user_id=user_id,
        role=role,
        status="active",
        user_email="user@example.com",
        user_name="User One",
        created_by_user_id="creator"
    )
    db.add(member)
    db.commit()
    db.refresh(member)
    return member


def _create_invitation(db, tenant_id="tenant-1", email="invitee@example.com", token="token-123"):
    invitation = OrganizationInvitation(
        tenant_id=tenant_id,
        email=email,
        role="member",
        invited_by_user_id="inviter-1",
        invited_by_name="Inviter One",
        token=token,
        status="pending",
        expires_at=datetime.now(timezone.utc) + timedelta(days=7)
    )
    db.add(invitation)
    db.commit()
    db.refresh(invitation)
    return invitation


@pytest.fixture
def org_client(db):
    def override_get_db():
        try:
            yield db
        finally:
            pass

    async def override_get_current_user_id():
        return "user-1"

    async def override_get_current_tenant_id():
        return "tenant-1"

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user_id] = override_get_current_user_id
    app.dependency_overrides[get_current_tenant_id] = override_get_current_tenant_id

    client = TestClient(app)
    try:
        yield client
    finally:
        app.dependency_overrides.clear()


def test_invite_user_sends_invitation_email(org_client, db, monkeypatch):
    _create_tenant(db, tenant_id="tenant-1", name="Test Org")
    _create_member(db, tenant_id="tenant-1", user_id="user-1", role="owner")

    called = {}

    def fake_send_invitation_email(self, to_email, inviter_name, organization_name, invitation_token):
        called["args"] = {
            "to_email": to_email,
            "inviter_name": inviter_name,
            "organization_name": organization_name,
            "invitation_token": invitation_token
        }
        return True

    monkeypatch.setattr(EmailService, "send_invitation_email", fake_send_invitation_email)

    response = org_client.post(
        "/api/organizations/current/invitations",
        json={"email": "invitee@example.com", "role": "member"}
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["email"] == "invitee@example.com"
    assert payload["role"] == "member"
    assert payload["status"] == "pending"
    assert payload["invited_by_name"] == "Team member"

    invitation = db.query(OrganizationInvitation).filter_by(email="invitee@example.com").first()
    assert invitation is not None
    assert called["args"]["to_email"] == "invitee@example.com"
    assert called["args"]["inviter_name"] == "Team member"
    assert called["args"]["organization_name"] == "Test Org"
    assert called["args"]["invitation_token"] == invitation.token


def test_invite_user_requires_admin_or_owner(org_client, db):
    _create_tenant(db, tenant_id="tenant-1", name="Test Org")
    _create_member(db, tenant_id="tenant-1", user_id="user-1", role="viewer")

    response = org_client.post(
        "/api/organizations/current/invitations",
        json={"email": "invitee@example.com", "role": "member"}
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Only owners and admins can invite users"


def test_list_pending_invitations_requires_admin_or_owner(org_client, db):
    _create_tenant(db, tenant_id="tenant-1", name="Test Org")
    _create_member(db, tenant_id="tenant-1", user_id="user-1", role="viewer")

    response = org_client.get("/api/organizations/current/invitations")

    assert response.status_code == 403
    assert response.json()["detail"] == "Only owners and admins can view invitations"


def test_accept_invitation_creates_member(org_client, db):
    _create_tenant(db, tenant_id="tenant-1", name="Test Org")
    invitation = _create_invitation(db, tenant_id="tenant-1", token="token-abc")

    response = org_client.post(f"/api/organizations/invitations/{invitation.token}/accept")

    assert response.status_code == 200
    payload = response.json()
    assert payload["user_id"] == "user-1"
    assert payload["role"] == "member"
    assert payload["status"] == "active"
