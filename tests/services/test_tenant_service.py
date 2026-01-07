from types import SimpleNamespace
from unittest.mock import MagicMock

from avanamy.services.tenant_service import get_or_create_tenant


def test_get_or_create_tenant_returns_existing():
    existing = SimpleNamespace(id="tenant-1")
    query = MagicMock()
    query.filter.return_value.first.return_value = existing

    db = MagicMock()
    db.query.return_value = query

    tenant = get_or_create_tenant(db, tenant_id="tenant-1", name="Existing")

    assert tenant is existing
    db.add.assert_not_called()


def test_get_or_create_tenant_creates_new():
    query = MagicMock()
    query.filter.return_value.first.return_value = None

    db = MagicMock()
    db.query.return_value = query

    tenant = get_or_create_tenant(db, tenant_id="tenant-abcdef", name="New Name")

    assert tenant.id == "tenant-abcdef"
    assert tenant.slug == "tenant-a"
    db.add.assert_called_once()
    db.commit.assert_called_once()
    db.refresh.assert_called_once()
