import json
import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from avanamy.services.api_spec_service import (
    store_api_spec_file,
    update_api_spec_file,
)


class DummyQuery:
    """Minimal query stub that supports .filter(...).first()."""

    def __init__(self, result):
        self.result = result

    def filter(self, *_, **__):
        return self

    def first(self):
        return self.result

    def one_or_none(self):
        return self.result
    
def _stub_db(product, tenant, provider):
    db = MagicMock()

    def query(model):
        if getattr(model, "__name__", None) == "ApiProduct":
            return DummyQuery(product)
        if getattr(model, "__name__", None) == "Tenant":
            return DummyQuery(tenant)
        if getattr(model, "__name__", None) == "Provider":
            return DummyQuery(provider)
        return DummyQuery(None)

    db.query.side_effect = query
    return db


def test_store_api_spec_file_sets_version_and_paths(monkeypatch):
    tenant_id = uuid.uuid4()
    provider_id = uuid.uuid4()
    product_id = uuid.uuid4()

    tenant = SimpleNamespace(id=tenant_id, slug="tenant-a")
    provider = SimpleNamespace(id=provider_id, slug="provider-a")
    product = SimpleNamespace(
        id=product_id,
        slug="product-a",
        tenant_id=tenant_id,
        provider_id=provider_id,
    )

    spec = SimpleNamespace(
        id=uuid.uuid4(),
        name="Spec Name",
        api_product_id=product_id,
        provider_id=provider_id,
        tenant_id=tenant_id,
        parsed_schema=None,
        original_file_s3_path=None,
        version=None,
    )

    db = _stub_db(product, tenant, provider)

    mock_upload = MagicMock(return_value=("temp-key", "s3://temp/temp-key"))
    mock_copy = MagicMock()
    mock_delete = MagicMock()
    mock_docgen = MagicMock()
    mock_version = SimpleNamespace(version=1)

    monkeypatch.setattr(
        "avanamy.services.api_spec_service.upload_bytes",
        mock_upload,
    )
    monkeypatch.setattr(
        "avanamy.services.api_spec_service.copy_s3_object",
        mock_copy,
    )
    monkeypatch.setattr(
        "avanamy.services.api_spec_service.delete_s3_object",
        mock_delete,
    )
    monkeypatch.setattr(
        "avanamy.services.api_spec_service.generate_and_store_markdown_for_spec",
        mock_docgen,
    )
    monkeypatch.setattr(
        "avanamy.services.api_spec_service.VersionHistoryRepository.create",
        lambda db, api_spec_id, changelog=None, diff=None: mock_version,
    )
    monkeypatch.setattr(
        "avanamy.services.api_spec_service.parse_api_spec",
        lambda filename, raw: {"info": {"title": filename}},
    )
    monkeypatch.setattr(
        "avanamy.services.api_spec_service.normalize_api_spec",
        lambda parsed: parsed,
    )
    monkeypatch.setattr(
        "avanamy.services.api_spec_service.ApiSpecRepository.create",
        lambda db, **kwargs: spec,
    )

    result = store_api_spec_file(
        db=db,
        file_bytes=b'{"openapi": "3.0.0", "info": {"title": "X"}, "paths": {}}',
        filename="spec.json",
        content_type="application/json",
        tenant_id=str(tenant_id),
        api_product_id=str(product_id),
        provider_id=str(provider_id),
        description="demo",
    )

    assert result.version == "v1"
    assert mock_upload.call_count == 1
    # Dest key should contain tenant/provider/product slug + v1
    dest_key = mock_copy.call_args[0][1]
    assert "tenants/tenant-a" in dest_key
    assert "/providers/provider-a/" in dest_key
    assert "/api_products/product-a/versions/v1/" in dest_key
    mock_delete.assert_called_once()
    mock_docgen.assert_called_once_with(db, spec)


def test_store_api_spec_file_handles_parse_failure(monkeypatch):
    tenant_id = uuid.uuid4()
    provider_id = uuid.uuid4()
    product_id = uuid.uuid4()

    tenant = SimpleNamespace(id=tenant_id, slug="tenant-a")
    provider = SimpleNamespace(id=provider_id, slug="provider-a")
    product = SimpleNamespace(
        id=product_id,
        slug="product-a",
        tenant_id=tenant_id,
        provider_id=provider_id,
    )

    spec = SimpleNamespace(
        id=uuid.uuid4(),
        name="Spec Name",
        api_product_id=product_id,
        provider_id=provider_id,
        tenant_id=tenant_id,
        parsed_schema=None,
        original_file_s3_path=None,
        version=None,
    )

    db = _stub_db(product, tenant, provider)

    monkeypatch.setattr(
        "avanamy.services.api_spec_service.upload_bytes",
        lambda key, data, content_type=None: (key, f"s3://bucket/{key}"),
    )
    monkeypatch.setattr(
        "avanamy.services.api_spec_service.copy_s3_object",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "avanamy.services.api_spec_service.delete_s3_object",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "avanamy.services.api_spec_service.generate_and_store_markdown_for_spec",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "avanamy.services.api_spec_service.VersionHistoryRepository.create",
        lambda db, api_spec_id, changelog=None, diff=None: SimpleNamespace(version=1),
    )
    monkeypatch.setattr(
        "avanamy.services.api_spec_service.parse_api_spec",
        side_effect := MagicMock(side_effect=ValueError("boom")),
    )
    monkeypatch.setattr(
        "avanamy.services.api_spec_service.normalize_api_spec",
        lambda parsed: parsed,
    )
    monkeypatch.setattr(
        "avanamy.services.api_spec_service.ApiSpecRepository.create",
        lambda db, **kwargs: spec,
    )

    result = store_api_spec_file(
        db=db,
        file_bytes=b"invalid",
        filename="spec.yaml",
        content_type="application/yaml",
        tenant_id=str(tenant_id),
        api_product_id=str(product_id),
        provider_id=str(provider_id),
    )

    # parsed_schema stays None when parse fails
    assert result.parsed_schema is None
    assert result.version == "v1"
    assert side_effect.call_count == 1


def test_update_api_spec_file_updates_version_and_schema(monkeypatch):
    tenant_id = uuid.uuid4()
    provider_id = uuid.uuid4()
    product_id = uuid.uuid4()

    tenant = SimpleNamespace(id=tenant_id, slug="tenant-a")
    provider = SimpleNamespace(id=provider_id, slug="provider-a")
    product = SimpleNamespace(
        id=product_id,
        slug="product-a",
        tenant_id=tenant_id,
        provider_id=provider_id,
    )

    class Spec:
        def __init__(self):
            self.id = uuid.uuid4()
            self.api_product_id = product_id
            self.name = "Spec"
            self.description = "old"
            self.parsed_schema = None
            self.version = "v1"

    spec = Spec()
    db = _stub_db(product, tenant, provider)
    db.commit = MagicMock()
    db.refresh = MagicMock()

    monkeypatch.setattr(
        "avanamy.services.api_spec_service.parse_api_spec",
        lambda filename, raw: {"paths": {"root": {}}}
    )
    monkeypatch.setattr(
        "avanamy.services.api_spec_service.normalize_api_spec",
        lambda parsed: parsed,
    )
    monkeypatch.setattr(
        "avanamy.services.api_spec_service.VersionHistoryRepository.create",
        lambda db, api_spec_id, diff=None, changelog=None: SimpleNamespace(version=2),
    )
    upload_calls = MagicMock(return_value=("k", "s3://bucket/k"))
    monkeypatch.setattr(
        "avanamy.services.api_spec_service.upload_bytes",
        upload_calls,
    )
    monkeypatch.setattr(
        "avanamy.services.api_spec_service.regenerate_all_docs_for_spec",
        MagicMock(),
    )

    updated = update_api_spec_file(
        db=db,
        spec=spec,
        file_bytes=b'{"paths": {}}',
        filename="spec.json",
        content_type="application/json",
        tenant_id=str(tenant_id),
        version=None,
        description="new desc",
    )

    assert updated.version == "v2"
    assert updated.description == "new desc"
    assert json.loads(updated.parsed_schema)["paths"] == {"root": {}}
    upload_calls.assert_called_once()
