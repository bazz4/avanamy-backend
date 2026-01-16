from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from avanamy.api.routes.providers import (
    ProviderCreate,
    ProviderUpdate,
    create_provider,
    update_provider,
    delete_provider,
    update_provider_status,
)


@pytest.mark.anyio
async def test_create_provider_success():
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None

    payload = ProviderCreate(
        name=" Provider ",
        slug=" slug ",
        website=" ",
        logo_url="",
        description=" desc ",
    )

    provider = await create_provider(payload, user_id="user-1", tenant_id="tenant-1", db=db)

    assert provider.name == "Provider"
    assert provider.slug == "slug"
    assert provider.website is None
    assert provider.description == "desc"
    db.add.assert_called_once()


@pytest.mark.anyio
async def test_create_provider_conflict():
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = SimpleNamespace(id="p1")

    payload = ProviderCreate(name="P", slug="slug", website=None, logo_url=None, description=None)

    with pytest.raises(HTTPException) as exc:
        await create_provider(payload, user_id="user-1", tenant_id="tenant-1", db=db)

    assert exc.value.status_code == 400


@pytest.mark.anyio
async def test_update_provider_not_found():
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None

    with pytest.raises(HTTPException) as exc:
        await update_provider(
            provider_id="p1",
            provider_data=ProviderUpdate(name="X"),
            user_id="user-1",
            tenant_id="tenant-1",
            db=db,
        )

    assert exc.value.status_code == 404


@pytest.mark.anyio
async def test_update_provider_slug_conflict():
    provider = SimpleNamespace(id="p1", tenant_id="tenant-1", slug="old")
    conflict = SimpleNamespace(id="p2")

    query_provider = MagicMock()
    query_provider.filter.return_value.first.return_value = provider
    query_conflict = MagicMock()
    query_conflict.filter.return_value.first.return_value = conflict

    db = MagicMock()
    db.query.side_effect = [query_provider, query_conflict]

    with pytest.raises(HTTPException) as exc:
        await update_provider(
            provider_id="p1",
            provider_data=ProviderUpdate(slug="new"),
            user_id="user-1",
            tenant_id="tenant-1",
            db=db,
        )

    assert exc.value.status_code == 400


@pytest.mark.anyio
async def test_update_provider_success():
    provider = SimpleNamespace(
        id="p1",
        tenant_id="tenant-1",
        slug="old",
        name="Old",
        updated_by_user_id=None,
    )

    query_provider = MagicMock()
    query_provider.filter.return_value.first.return_value = provider
    query_conflict = MagicMock()
    query_conflict.filter.return_value.first.return_value = None

    db = MagicMock()
    db.query.side_effect = [query_provider, query_conflict]

    updated = await update_provider(
        provider_id="p1",
        provider_data=ProviderUpdate(name="New"),
        user_id="user-1",
        tenant_id="tenant-1",
        db=db,
    )

    assert updated.name == "New"
    assert provider.updated_by_user_id == "user-1"


@pytest.mark.anyio
async def test_delete_provider_with_products():
    provider = SimpleNamespace(id="p1", tenant_id="tenant-1")

    query_provider = MagicMock()
    query_provider.filter.return_value.first.return_value = provider
    query_products = MagicMock()
    query_products.filter.return_value.count.return_value = 2

    db = MagicMock()
    db.query.side_effect = [query_provider, query_products]

    with pytest.raises(HTTPException) as exc:
        await delete_provider(provider_id="p1", tenant_id="tenant-1", db=db)

    assert exc.value.status_code == 400


@pytest.mark.anyio
async def test_update_provider_status_invalid():
    with pytest.raises(HTTPException) as exc:
        await update_provider_status(
            provider_id="p1",
            status="bad",
            tenant_id="tenant-1",
            db=MagicMock(),
        )

    assert exc.value.status_code == 400
