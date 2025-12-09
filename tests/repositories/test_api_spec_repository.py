import json
from types import SimpleNamespace
from unittest.mock import MagicMock

from avanamy.repositories.api_spec_repository import ApiSpecRepository


def test_create_api_spec_commits_and_serializes(monkeypatch):
    fake_db = MagicMock()
    fake_db.add = MagicMock()
    fake_db.commit = MagicMock()
    fake_db.refresh = MagicMock()

    spec = ApiSpecRepository.create(
        fake_db,
        tenant_id="tenant-1",
        api_product_id="product-1",
        provider_id="provider-1",
        name="Test API",
        version="1.0",
        description="demo",
        original_file_s3_path="s3://test.json",
        parsed_schema={"info": "test"},
    )

    fake_db.add.assert_called_once()
    fake_db.commit.assert_called_once()
    fake_db.refresh.assert_called_once_with(spec)
    assert json.loads(spec.parsed_schema)["info"] == "test"
    assert spec.api_product_id == "product-1"


def test_get_by_id_uses_filters(monkeypatch):
    fake_db = MagicMock()
    fake_spec = SimpleNamespace(id="spec-1")
    fake_db.query.return_value.filter.return_value.first.return_value = fake_spec

    result = ApiSpecRepository.get_by_id(fake_db, "spec-1", "tenant-1")
    assert result is fake_spec
    fake_db.query.return_value.filter.assert_called_once()


def test_list_for_tenant_orders_desc(monkeypatch):
    fake_db = MagicMock()
    fake_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = ["a", "b"]
    out = ApiSpecRepository.list_for_tenant(fake_db, "tenant-1")
    assert out == ["a", "b"]


def test_update_api_spec_sets_fields():
    fake_db = MagicMock()
    spec = SimpleNamespace(
        id="spec-1",
        tenant_id="tenant-1",
        version="v1",
        description="old",
        parsed_schema=None,
        original_file_s3_path="s3://old",
        updated_by_user_id=None,
    )

    updated = ApiSpecRepository.update(
        fake_db,
        spec=spec,
        parsed_schema={"new": True},
        description="new desc",
        version_label="v2",
        original_file_s3_path="s3://new",
        updated_by_user_id="user-1",
    )

    assert updated.version == "v2"
    assert updated.description == "new desc"
    assert updated.original_file_s3_path == "s3://new"
    assert json.loads(updated.parsed_schema)["new"] is True
    fake_db.commit.assert_called_once()
    fake_db.refresh.assert_called_once_with(spec)


def test_delete_api_spec_handles_missing():
    fake_db = MagicMock()
    fake_db.query.return_value.filter.return_value.first.return_value = None
    assert ApiSpecRepository.delete(fake_db, "spec-1", "tenant-1") is False

    # now simulate existing spec
    fake_db = MagicMock()
    fake_db.query.return_value.filter.return_value.first.return_value = SimpleNamespace(id="spec-1")
    assert ApiSpecRepository.delete(fake_db, "spec-1", "tenant-1") is True
    fake_db.delete.assert_called_once()
    fake_db.commit.assert_called_once()
