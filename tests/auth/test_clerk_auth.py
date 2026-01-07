from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from avanamy.auth import clerk as clerk_auth


@pytest.mark.anyio
async def test_get_current_user_id_success(monkeypatch):
    credentials = HTTPAuthorizationCredentials(
        scheme="Bearer",
        credentials="token",
    )

    monkeypatch.setattr(
        "jose.jwt.decode",
        lambda *_args, **_kwargs: {"sub": "user-1"},
    )

    user_id = await clerk_auth.get_current_user_id(credentials)

    assert user_id == "user-1"


@pytest.mark.anyio
async def test_get_current_user_id_missing_sub(monkeypatch):
    credentials = HTTPAuthorizationCredentials(
        scheme="Bearer",
        credentials="token",
    )

    monkeypatch.setattr(
        "jose.jwt.decode",
        lambda *_args, **_kwargs: {},
    )

    with pytest.raises(HTTPException) as exc:
        await clerk_auth.get_current_user_id(credentials)

    assert exc.value.status_code == 401


@pytest.mark.anyio
async def test_get_current_user_id_decode_error(monkeypatch):
    credentials = HTTPAuthorizationCredentials(
        scheme="Bearer",
        credentials="token",
    )

    def _raise(*_args, **_kwargs):
        raise Exception("bad token")

    monkeypatch.setattr("jose.jwt.decode", _raise)

    with pytest.raises(HTTPException) as exc:
        await clerk_auth.get_current_user_id(credentials)

    assert exc.value.status_code == 401


@pytest.mark.anyio
async def test_get_current_tenant_id_org(monkeypatch):
    user = SimpleNamespace(
        organization_memberships=[
            SimpleNamespace(organization=SimpleNamespace(id="org-1", name="Org"))
        ],
        email_addresses=[],
        first_name="",
        last_name="",
    )

    monkeypatch.setattr(
        "avanamy.auth.clerk.clerk.users.get",
        lambda user_id: user,
    )

    monkeypatch.setattr(
        "avanamy.auth.clerk.get_or_create_tenant",
        lambda _db, tenant_id, name, is_organization: SimpleNamespace(id=tenant_id),
    )

    tenant_id = await clerk_auth.get_current_tenant_id(
        user_id="user-1",
        db=MagicMock(),
    )

    assert tenant_id == "org-1"


@pytest.mark.anyio
async def test_get_current_tenant_id_personal(monkeypatch):
    user = SimpleNamespace(
        organization_memberships=[],
        email_addresses=[SimpleNamespace(email_address="user@example.com")],
        first_name="First",
        last_name="Last",
    )

    monkeypatch.setattr(
        "avanamy.auth.clerk.clerk.users.get",
        lambda user_id: user,
    )

    monkeypatch.setattr(
        "avanamy.auth.clerk.get_or_create_tenant",
        lambda _db, tenant_id, name, is_organization: SimpleNamespace(id=tenant_id),
    )

    tenant_id = await clerk_auth.get_current_tenant_id(
        user_id="user-1",
        db=MagicMock(),
    )

    assert tenant_id == "user-1"


@pytest.mark.anyio
async def test_get_current_tenant_id_clerk_error_fallback(monkeypatch):
    def _raise(*_args, **_kwargs):
        raise Exception("clerk down")

    monkeypatch.setattr(
        "avanamy.auth.clerk.clerk.users.get",
        _raise,
    )

    monkeypatch.setattr(
        "avanamy.auth.clerk.get_or_create_tenant",
        lambda _db, tenant_id, name, is_organization: SimpleNamespace(id=tenant_id),
    )

    tenant_id = await clerk_auth.get_current_tenant_id(
        user_id="user-abc12345",
        db=MagicMock(),
    )

    assert tenant_id == "user-abc12345"
