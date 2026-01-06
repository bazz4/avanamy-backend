import json
import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock, AsyncMock, patch

import pytest

from avanamy.models.api_spec import ApiSpec
from avanamy.models.version_history import VersionHistory
from avanamy.services.api_spec_service import (
    store_api_spec_file,
    update_api_spec_file,
)

pytestmark = pytest.mark.anyio


def _uuid_str(u):
    """
    SQLite + SQLAlchemy's Postgres UUID type expect .hex; provide a str-like
    value with a .hex property for UUID bindings while keeping API input as str.
    """
    class UUIDStr(str):
        @property
        def hex(self):
            return uuid.UUID(str(self)).hex
    return UUIDStr(str(u))


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


async def test_store_api_spec_file_sets_version_and_paths(monkeypatch):
    tenant_id = "tenant_test123"
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
    mock_docgen = AsyncMock()
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

    result = await store_api_spec_file(
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
    mock_docgen.assert_awaited_once_with(db, spec)


async def test_store_api_spec_file_handles_parse_failure(monkeypatch):
    tenant_id = "tenant_test123"
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
    async def _noop(*args, **kwargs):
        return None

    monkeypatch.setattr(
        "avanamy.services.api_spec_service.generate_and_store_markdown_for_spec",
        _noop,
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

    result = await store_api_spec_file(
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


async def test_update_api_spec_file_updates_version_and_schema(monkeypatch):
    tenant_id = "tenant_test123"
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
        AsyncMock(),
    )

    updated = await update_api_spec_file(
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


async def test_store_api_spec_file_reuses_existing_spec_for_same_product(
    db,
    tenant_provider_product,
    monkeypatch,
):
    """
    Verify that uploading a spec for the same tenant + provider + api_product
    reuses the existing ApiSpec instead of creating a new one.

    Business rules:
    - Each ApiProduct can have only one ApiSpec
    - Uploading a spec for the same tenant + provider + api_product must reuse the existing ApiSpec
    - No new ApiSpec row should be created
    - A new VersionHistory row should be created
    """
    tenant, provider, product = tenant_provider_product

    # -------------------------
    # Stub S3 operations so nothing touches real storage
    # -------------------------
    monkeypatch.setattr(
        "avanamy.services.api_spec_service.upload_bytes",
        lambda *args, **kwargs: ("s3/key", "s3://bucket/s3/key"),
    )
    monkeypatch.setattr(
        "avanamy.services.api_spec_service.copy_s3_object",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "avanamy.services.api_spec_service.delete_s3_object",
        lambda *args, **kwargs: None,
    )

    # Silence doc generation
    async def _noop(*args, **kwargs):
        return None

    monkeypatch.setattr(
        "avanamy.services.api_spec_service.generate_and_store_markdown_for_spec",
        _noop,
    )
    monkeypatch.setattr(
        "avanamy.services.api_spec_service.regenerate_all_docs_for_spec",
        _noop,
    )

    # Silence normalized spec and diff services
    monkeypatch.setattr(
        "avanamy.services.normalized_spec_service.generate_and_store_normalized_spec",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "avanamy.services.version_diff_service.compute_and_store_diff",
        lambda *args, **kwargs: None,
    )

    # Stub parse and normalize functions
    monkeypatch.setattr(
        "avanamy.services.api_spec_service.parse_api_spec",
        lambda filename, raw: {
            "openapi": "3.0.0",
            "info": {"title": "Test"},
            "paths": {
                "/test": {
                    "get": {
                        "responses": {
                            "200": {
                                "content": {
                                    "application/json": {
                                        "schema": {
                                            "type": "object",
                                            "required": ["id"]
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        },
    )
    monkeypatch.setattr(
        "avanamy.services.api_spec_service.normalize_api_spec",
        lambda parsed: parsed,
    )

    # -------------------------
    # Prepare repository fakes and counters
    # -------------------------
    created_specs = []

    def _create_side_effect(db_session, **kwargs):
        import uuid as _uuid
        from avanamy.models.api_spec import ApiSpec

        # Create a real ApiSpec instance so it can be committed
        spec_obj = ApiSpec(
            id=_uuid.uuid4(),
            tenant_id=kwargs.get("tenant_id"),
            api_product_id=kwargs.get("api_product_id"),
            provider_id=kwargs.get("provider_id"),
            name=kwargs.get("name"),
            parsed_schema=kwargs.get("parsed_schema"),
            original_file_s3_path=kwargs.get("original_file_s3_path"),
            version=None,
        )
        db_session.add(spec_obj)
        db_session.commit()
        db_session.refresh(spec_obj)
        created_specs.append(spec_obj)
        return spec_obj

    create_mock = MagicMock(side_effect=_create_side_effect)
    monkeypatch.setattr(
        "avanamy.services.api_spec_service.ApiSpecRepository.create",
        create_mock,
    )

    # get_by_product returns the created spec once available
    def _get_by_product(db_session, tenant_id, api_product_id, provider_id=None):
        return created_specs[0] if created_specs else None

    monkeypatch.setattr(
        "avanamy.services.api_spec_service.ApiSpecRepository.get_by_product",
        _get_by_product,
    )

    # VersionHistory create should be called twice; return incremental versions
    vh_counter = {"n": 0}

    def _vh_side_effect(db, api_spec_id, changelog=None, diff=None):
        vh_counter["n"] += 1
        return SimpleNamespace(version=vh_counter["n"])

    vh_mock = MagicMock(side_effect=_vh_side_effect)
    monkeypatch.setattr(
        "avanamy.services.api_spec_service.VersionHistoryRepository.create",
        vh_mock,
    )

    # -------------------------
    # Call service twice using real UUID objects
    # -------------------------
    spec1 = await store_api_spec_file(
        db=db,
        tenant_id=tenant.id,
        provider_id=_uuid_str(provider.id),
        api_product_id=_uuid_str(product.id),
        filename="spec.yaml",
        file_bytes=b"openapi: 3.0.0\ninfo:\n  title: Test\npaths: {}",
        content_type="application/yaml",
        name="Menu API",
    )

    spec2 = await store_api_spec_file(
        db=db,
        tenant_id=tenant.id,
        provider_id=_uuid_str(provider.id),
        api_product_id=_uuid_str(product.id),
        filename="spec.yaml",
        file_bytes=b"openapi: 3.0.0\ninfo:\n  title: Test v2\npaths: {}",
        content_type="application/yaml",
        name="Menu API",
    )

    # -------------------------
    # Assertions per business rules
    # -------------------------
    # Same ApiSpec reused
    assert str(spec1.id) == str(spec2.id)

    # ApiSpecRepository.create should have been called only once
    assert create_mock.call_count == 1

    # VersionHistoryRepository.create should have been invoked twice
    assert vh_mock.call_count == 2


async def test_store_api_spec_file_reuses_existing_spec_real_db(db, tenant_provider_product, monkeypatch):
    tenant, provider, product = tenant_provider_product

    # Silence S3 + doc generation side effects
    monkeypatch.setattr(
        "avanamy.services.api_spec_service.upload_bytes",
        lambda *args, **kwargs: ("tmp/key", "s3://bucket/tmp/key"),
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
        "avanamy.services.api_spec_service.generate_s3_url",
        lambda key: f"s3://bucket/{key}",
    )
    async def _noop(*args, **kwargs):
        return None

    monkeypatch.setattr(
        "avanamy.services.api_spec_service.generate_and_store_markdown_for_spec",
        _noop,
    )
    monkeypatch.setattr(
        "avanamy.services.api_spec_service.regenerate_all_docs_for_spec",
        _noop,
    )

    # Silence normalized spec and diff services
    monkeypatch.setattr(
        "avanamy.services.normalized_spec_service.generate_and_store_normalized_spec",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "avanamy.services.version_diff_service.compute_and_store_diff",
        lambda *args, **kwargs: None,
    )

    payload = b"openapi: 3.0.0\ninfo:\n  title: Test\npaths: {}"

    spec1 = await store_api_spec_file(
        db=db,
        tenant_id=tenant.id,
        provider_id=_uuid_str(provider.id),
        api_product_id=_uuid_str(product.id),
        filename="spec.yaml",
        file_bytes=payload,
        content_type="application/yaml",
        name="Menu API",
    )

    spec2 = await store_api_spec_file(
        db=db,
        tenant_id=tenant.id,
        provider_id=_uuid_str(provider.id),
        api_product_id=_uuid_str(product.id),
        filename="spec.yaml",
        file_bytes=payload,
        content_type="application/yaml",
        name="Menu API",
    )

    all_specs = db.query(ApiSpec).all()
    assert len(all_specs) == 1
    assert spec1.id == spec2.id

    versions = db.query(VersionHistory).filter(VersionHistory.api_spec_id == spec1.id).all()
    assert len(versions) == 2


async def test_store_api_spec_file_creates_new_spec_for_different_products(db, tenant_provider_product, monkeypatch):
    tenant, provider, product_a = tenant_provider_product

    # Create a second product under the same tenant/provider
    from avanamy.models.api_product import ApiProduct

    product_b = ApiProduct(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        provider_id=provider.id,
        name="Second Product",
        slug="second-product",
    )
    db.add(product_b)
    db.commit()
    db.refresh(product_b)

    monkeypatch.setattr(
        "avanamy.services.api_spec_service.upload_bytes",
        lambda *args, **kwargs: ("tmp/key", "s3://bucket/tmp/key"),
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
        "avanamy.services.api_spec_service.generate_s3_url",
        lambda key: f"s3://bucket/{key}",
    )
    async def _noop(*args, **kwargs):
        return None

    monkeypatch.setattr(
        "avanamy.services.api_spec_service.generate_and_store_markdown_for_spec",
        _noop,
    )
    monkeypatch.setattr(
        "avanamy.services.api_spec_service.regenerate_all_docs_for_spec",
        _noop,
    )

    # Silence normalized spec and diff services
    monkeypatch.setattr(
        "avanamy.services.normalized_spec_service.generate_and_store_normalized_spec",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "avanamy.services.version_diff_service.compute_and_store_diff",
        lambda *args, **kwargs: None,
    )

    payload_a = b"openapi: 3.0.0\ninfo:\n  title: Product A\npaths: {}"
    payload_b = b"openapi: 3.0.0\ninfo:\n  title: Product B\npaths: {}"

    spec_a = await store_api_spec_file(
        db=db,
        tenant_id=tenant.id,
        provider_id=_uuid_str(provider.id),
        api_product_id=_uuid_str(product_a.id),
        filename="spec-a.yaml",
        file_bytes=payload_a,
        content_type="application/yaml",
        name="Menu API A",
    )

    spec_b = await store_api_spec_file(
        db=db,
        tenant_id=tenant.id,
        provider_id=_uuid_str(provider.id),
        api_product_id=_uuid_str(product_b.id),
        filename="spec-b.yaml",
        file_bytes=payload_b,
        content_type="application/yaml",
        name="Menu API B",
    )

    all_specs = db.query(ApiSpec).all()
    assert len(all_specs) == 2


async def test_update_api_spec_file_calls_store_original_spec_artifact(monkeypatch):
    """Test that update_api_spec_file calls store_original_spec_artifact for new versions."""
    tenant_id = "tenant_test123"
    provider_id = uuid.uuid4()
    product_id = uuid.uuid4()
    spec_id = uuid.uuid4()
    version_history_id = 5

    tenant = SimpleNamespace(id=tenant_id, slug="tenant-a")
    provider = SimpleNamespace(id=provider_id, slug="provider-a")
    product = SimpleNamespace(
        id=product_id,
        slug="product-a",
        tenant_id=tenant_id,
        provider_id=provider_id,
    )

    spec = SimpleNamespace(
        id=spec_id,
        name="Test Spec",
        api_product_id=product_id,
        provider_id=provider_id,
        tenant_id=tenant_id,
        parsed_schema='{"paths": {}}',
        original_file_s3_path="s3://bucket/old/path",
        version="v1",
        description="Original desc",
    )

    db = _stub_db(product, tenant, provider)
    version_history = SimpleNamespace(id=version_history_id, version=2)

    # Track calls to store_original_spec_artifact
    store_artifact_calls = []

    def mock_store_original_spec_artifact(db, **kwargs):
        store_artifact_calls.append(kwargs)

    monkeypatch.setattr(
        "avanamy.services.original_spec_artifact_service.store_original_spec_artifact",
        mock_store_original_spec_artifact,
    )

    monkeypatch.setattr(
        "avanamy.services.api_spec_service.parse_api_spec",
        lambda filename, raw: {"paths": {}},
    )
    monkeypatch.setattr(
        "avanamy.services.api_spec_service.normalize_api_spec",
        lambda parsed: parsed,
    )
    monkeypatch.setattr(
        "avanamy.services.api_spec_service.VersionHistoryRepository.create",
        lambda db, api_spec_id, diff=None, changelog=None: version_history,
    )
    monkeypatch.setattr(
        "avanamy.services.api_spec_service.upload_bytes",
        lambda *args, **kwargs: ("final-key", "s3://bucket/final-key"),
    )
    monkeypatch.setattr(
        "avanamy.services.api_spec_service.regenerate_all_docs_for_spec",
        AsyncMock(),
    )
    monkeypatch.setattr(
        "avanamy.services.normalized_spec_service.generate_and_store_normalized_spec",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "avanamy.services.version_diff_service.compute_and_store_diff",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "avanamy.services.spec_normalizer.normalize_openapi_spec",
        lambda spec: spec,
    )

    await update_api_spec_file(
        db=db,
        spec=spec,
        file_bytes=b'{"paths": {}}',
        filename="spec.json",
        content_type="application/json",
        tenant_id=str(tenant_id),
        description="Updated desc",
    )

    # Verify store_original_spec_artifact was called
    assert len(store_artifact_calls) == 1
    call_kwargs = store_artifact_calls[0]
    assert call_kwargs["tenant_id"] == tenant_id
    assert call_kwargs["api_spec_id"] == spec_id
    assert call_kwargs["version_history_id"] == version_history_id
    # The s3_path is the constructed key path, not the raw return value
    assert "tenant-a" in call_kwargs["s3_path"]
    assert "provider-a" in call_kwargs["s3_path"]
    assert "product-a" in call_kwargs["s3_path"]
    assert "v2" in call_kwargs["s3_path"]


async def test_update_api_spec_file_handles_artifact_storage_failure(monkeypatch):
    """Test that update_api_spec_file handles failures in store_original_spec_artifact gracefully."""
    tenant_id = "tenant_test123"
    provider_id = uuid.uuid4()
    product_id = uuid.uuid4()
    spec_id = uuid.uuid4()

    tenant = SimpleNamespace(id=tenant_id, slug="tenant-a")
    provider = SimpleNamespace(id=provider_id, slug="provider-a")
    product = SimpleNamespace(
        id=product_id,
        slug="product-a",
        tenant_id=tenant_id,
        provider_id=provider_id,
    )

    spec = SimpleNamespace(
        id=spec_id,
        name="Test Spec",
        api_product_id=product_id,
        provider_id=provider_id,
        tenant_id=tenant_id,
        parsed_schema='{"paths": {}}',
        original_file_s3_path="s3://bucket/old/path",
        version="v1",
        description="Original desc",
    )

    db = _stub_db(product, tenant, provider)

    # Mock store_original_spec_artifact to raise exception
    def mock_store_artifact_error(db, **kwargs):
        raise Exception("Artifact storage failed")

    monkeypatch.setattr(
        "avanamy.services.original_spec_artifact_service.store_original_spec_artifact",
        mock_store_artifact_error,
    )

    monkeypatch.setattr(
        "avanamy.services.api_spec_service.parse_api_spec",
        lambda filename, raw: {"paths": {}},
    )
    monkeypatch.setattr(
        "avanamy.services.api_spec_service.normalize_api_spec",
        lambda parsed: parsed,
    )
    monkeypatch.setattr(
        "avanamy.services.api_spec_service.VersionHistoryRepository.create",
        lambda db, api_spec_id, diff=None, changelog=None: SimpleNamespace(id=3, version=2),
    )
    monkeypatch.setattr(
        "avanamy.services.api_spec_service.upload_bytes",
        lambda *args, **kwargs: ("final-key", "s3://bucket/final-key"),
    )
    monkeypatch.setattr(
        "avanamy.services.api_spec_service.regenerate_all_docs_for_spec",
        AsyncMock(),
    )
    monkeypatch.setattr(
        "avanamy.services.normalized_spec_service.generate_and_store_normalized_spec",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "avanamy.services.version_diff_service.compute_and_store_diff",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "avanamy.services.spec_normalizer.normalize_openapi_spec",
        lambda spec: spec,
    )

    # Should not raise exception - the service should handle the failure gracefully
    result = await update_api_spec_file(
        db=db,
        spec=spec,
        file_bytes=b'{"paths": {}}',
        filename="spec.json",
        content_type="application/json",
        tenant_id=str(tenant_id),
        description="Updated desc",
    )

    # The update should still succeed
    assert result == spec


async def test_store_api_spec_file_does_not_call_original_spec_artifact_on_initial_upload(monkeypatch):
    """
    Test that store_api_spec_file (initial upload) does NOT call store_original_spec_artifact.

    Note: Based on the code, only update_api_spec_file calls store_original_spec_artifact.
    Initial uploads don't create original_spec artifacts yet.
    """
    tenant_id = "tenant_test123"
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

    # Track calls to store_original_spec_artifact
    store_artifact_calls = []

    def mock_store_original_spec_artifact(db, **kwargs):
        store_artifact_calls.append(kwargs)

    monkeypatch.setattr(
        "avanamy.services.original_spec_artifact_service.store_original_spec_artifact",
        mock_store_original_spec_artifact,
    )

    monkeypatch.setattr(
        "avanamy.services.api_spec_service.upload_bytes",
        MagicMock(return_value=("temp-key", "s3://temp/temp-key")),
    )
    monkeypatch.setattr(
        "avanamy.services.api_spec_service.copy_s3_object",
        MagicMock(),
    )
    monkeypatch.setattr(
        "avanamy.services.api_spec_service.delete_s3_object",
        MagicMock(),
    )
    monkeypatch.setattr(
        "avanamy.services.api_spec_service.generate_and_store_markdown_for_spec",
        AsyncMock(),
    )
    monkeypatch.setattr(
        "avanamy.services.api_spec_service.VersionHistoryRepository.create",
        lambda db, api_spec_id, changelog=None, diff=None: SimpleNamespace(version=1),
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
    monkeypatch.setattr(
        "avanamy.services.normalized_spec_service.generate_and_store_normalized_spec",
        lambda *args, **kwargs: None,
    )

    await store_api_spec_file(
        db=db,
        file_bytes=b'{"openapi": "3.0.0", "info": {"title": "X"}, "paths": {}}',
        filename="spec.json",
        content_type="application/json",
        tenant_id=str(tenant_id),
        api_product_id=str(product_id),
        provider_id=str(provider_id),
        description="demo",
    )

    # Verify store_original_spec_artifact was NOT called for initial upload
    assert len(store_artifact_calls) == 0
