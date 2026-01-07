from types import SimpleNamespace
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from avanamy.api.routes.products import (
    ApiProductCreate,
    ApiProductUpdate,
    create_api_product,
    update_api_product,
    update_product_status,
)


@pytest.mark.anyio
async def test_create_api_product_missing_provider():
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None

    payload = ApiProductCreate(
        name="Product",
        slug="slug",
        provider_id="provider-1",
        description=None,
    )

    with pytest.raises(HTTPException) as exc:
        await create_api_product(payload, tenant_id="tenant-1", db=db)

    assert exc.value.status_code == 400


@pytest.mark.anyio
async def test_create_api_product_slug_conflict():
    provider = SimpleNamespace(id="provider-1", tenant_id="tenant-1", name="P", slug="p")
    existing = SimpleNamespace(id="product-1")

    query_provider = MagicMock()
    query_provider.filter.return_value.first.return_value = provider
    query_existing = MagicMock()
    query_existing.filter.return_value.first.return_value = existing

    db = MagicMock()
    db.query.side_effect = [query_provider, query_existing]

    payload = ApiProductCreate(
        name="Product",
        slug="slug",
        provider_id="provider-1",
        description=None,
    )

    with pytest.raises(HTTPException) as exc:
        await create_api_product(payload, tenant_id="tenant-1", db=db)

    assert exc.value.status_code == 400


@pytest.mark.anyio
async def test_create_api_product_success():
    provider = SimpleNamespace(id="provider-1", tenant_id="tenant-1", name="P", slug="p")

    query_provider = MagicMock()
    query_provider.filter.return_value.first.return_value = provider
    query_existing = MagicMock()
    query_existing.filter.return_value.first.return_value = None

    db = MagicMock()
    db.query.side_effect = [query_provider, query_existing]
    def _refresh(obj):
        obj.created_at = obj.created_at or datetime.now(timezone.utc)
    db.refresh.side_effect = _refresh

    payload = ApiProductCreate(
        name=" Product ",
        slug=" slug ",
        provider_id="provider-1",
        description=" desc ",
    )

    product = await create_api_product(payload, tenant_id="tenant-1", db=db)

    assert product.name == "Product"
    assert product.slug == "slug"
    assert product.description == "desc"
    db.add.assert_called_once()


@pytest.mark.anyio
async def test_update_api_product_not_found():
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None

    with pytest.raises(HTTPException) as exc:
        await update_api_product(
            product_id="product-1",
            product_data=ApiProductUpdate(name="New"),
            tenant_id="tenant-1",
            db=db,
        )

    assert exc.value.status_code == 404


@pytest.mark.anyio
async def test_update_api_product_provider_missing():
    product = SimpleNamespace(id="product-1", tenant_id="tenant-1", provider_id="p1", slug="s")

    query_product = MagicMock()
    query_product.filter.return_value.first.return_value = product
    query_provider = MagicMock()
    query_provider.filter.return_value.first.return_value = None

    db = MagicMock()
    db.query.side_effect = [query_product, query_provider]

    with pytest.raises(HTTPException) as exc:
        await update_api_product(
            product_id="product-1",
            product_data=ApiProductUpdate(provider_id="p2"),
            tenant_id="tenant-1",
            db=db,
        )

    assert exc.value.status_code == 400


@pytest.mark.anyio
async def test_update_api_product_slug_conflict():
    product = SimpleNamespace(id="product-1", tenant_id="tenant-1", provider_id="p1", slug="old")
    conflict = SimpleNamespace(id="product-2")

    query_product = MagicMock()
    query_product.filter.return_value.first.return_value = product
    query_conflict = MagicMock()
    query_conflict.filter.return_value.first.return_value = conflict

    db = MagicMock()
    db.query.side_effect = [query_product, query_conflict]

    with pytest.raises(HTTPException) as exc:
        await update_api_product(
            product_id="product-1",
            product_data=ApiProductUpdate(slug="new"),
            tenant_id="tenant-1",
            db=db,
        )

    assert exc.value.status_code == 400


@pytest.mark.anyio
async def test_update_product_status_invalid():
    with pytest.raises(HTTPException) as exc:
        await update_product_status(
            product_id="product-1",
            status="bad",
            tenant_id="tenant-1",
            db=MagicMock(),
        )

    assert exc.value.status_code == 400
