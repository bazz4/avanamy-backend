import uuid

import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from avanamy.api.routes import spec_versions, spec_docs
from avanamy.models.api_spec import ApiSpec
from avanamy.models.documentation_artifact import DocumentationArtifact


def test_list_versions_for_spec(monkeypatch):
    tenant_id = "tenant-1"
    spec_id = uuid.uuid4()
    fake_db = MagicMock()

    fake_spec = SimpleNamespace(id=spec_id)
    fake_versions = [
        SimpleNamespace(version=1, changelog="init", created_at=SimpleNamespace(isoformat=lambda: "ts1"), diff=None, summary=None),
        SimpleNamespace(version=2, changelog="second", created_at=SimpleNamespace(isoformat=lambda: "ts2"), diff=None, summary=None),
    ]

    fake_db.query.return_value.join.return_value.join.return_value.filter.return_value.first.return_value = fake_spec
    fake_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = fake_versions

    result = spec_versions.list_versions_for_spec(
        spec_id=spec_id,
        tenant_id=tenant_id,
        db=fake_db,
    )
    assert [v["version"] for v in result] == [1, 2]
    assert result[1]["label"] == "v2"


def test_list_versions_respects_tenant(monkeypatch):
    fake_db = MagicMock()
    fake_db.query.return_value.join.return_value.join.return_value.filter.return_value.first.return_value = None

    with pytest.raises(HTTPException) as exc:
        spec_versions.list_versions_for_spec(
            spec_id=uuid.uuid4(),
            tenant_id="other-tenant",
            db=fake_db,
        )
    assert exc.value.status_code == 404


def test_spec_docs_endpoint_success(monkeypatch):
    tenant_id = "tenant-1"
    spec_id = uuid.uuid4()
    fake_db = MagicMock()

    fake_spec = SimpleNamespace(id=spec_id)
    fake_db.query.return_value.join.return_value.join.return_value.filter.return_value.first.return_value = fake_spec

    markdown_artifact = DocumentationArtifact(
        api_spec_id=spec_id,
        tenant_id=tenant_id,
        artifact_type="api_markdown",
        s3_path="s3://docs/md",
    )
    html_artifact = DocumentationArtifact(
        api_spec_id=spec_id,
        tenant_id=tenant_id,
        artifact_type="api_html",
        s3_path="s3://docs/html",
    )

    repo = MagicMock()
    repo.get_latest.side_effect = [markdown_artifact, html_artifact]
    monkeypatch.setattr(
        "avanamy.api.routes.spec_docs.DocumentationArtifactRepository",
        lambda: repo,
    )
    monkeypatch.setattr(
        "avanamy.api.routes.spec_docs.VersionHistoryRepository.current_version_label_for_spec",
        lambda db, _spec_id: "v3",
    )

    result = spec_docs.get_docs_for_spec(
        spec_id=spec_id,
        tenant_id=tenant_id,
        db=fake_db,
    )
    assert result.version == "v3"
    assert result.markdown_s3_url == "s3://docs/md"
    assert result.html_s3_url == "s3://docs/html"


def test_spec_docs_endpoint_not_found(monkeypatch):
    fake_db = MagicMock()
    fake_db.query.return_value.join.return_value.join.return_value.filter.return_value.first.return_value = None

    with pytest.raises(HTTPException) as exc:
        spec_docs.get_docs_for_spec(
            spec_id=uuid.uuid4(),
            tenant_id="tenant-1",
            db=fake_db,
        )
    assert exc.value.status_code == 404


# Tests for new endpoints: get_original_spec_for_version and compare_two_versions


def test_get_original_spec_for_version_success(monkeypatch):
    """Test successful retrieval of original spec for a version."""
    tenant_id = "tenant-1"
    spec_id = uuid.uuid4()
    version_number = 3
    version_history_id = 123

    fake_db = MagicMock()

    # Mock spec validation (tenant ownership check)
    fake_spec = SimpleNamespace(id=spec_id)
    fake_db.query.return_value.join.return_value.join.return_value.filter.return_value.first.return_value = fake_spec

    # Mock version history lookup
    fake_version = SimpleNamespace(id=version_history_id, version=version_number)

    # Mock artifact lookup
    fake_artifact = SimpleNamespace(
        s3_path="tenants/tenant-a/providers/provider-a/api_products/product-a/versions/v3/spec.json",
        artifact_type="original_spec",
        version_history_id=version_history_id,
    )

    # Set up query chains
    query_results = {
        "spec": fake_spec,
        "version": fake_version,
        "artifact": fake_artifact,
    }
    query_index = {"count": 0}

    def mock_query(model):
        query_index["count"] += 1
        call_num = query_index["count"]

        mock_chain = MagicMock()
        mock_chain.join.return_value = mock_chain
        mock_chain.filter.return_value = mock_chain

        if call_num == 1:
            # First call - spec lookup
            mock_chain.first.return_value = query_results["spec"]
        elif call_num == 2:
            # Second call - version history lookup
            mock_chain.first.return_value = query_results["version"]
        elif call_num == 3:
            # Third call - artifact lookup
            mock_chain.first.return_value = query_results["artifact"]
        else:
            mock_chain.first.return_value = None

        return mock_chain

    fake_db.query.side_effect = mock_query

    # Mock S3 download
    spec_data = {"openapi": "3.0.0", "paths": {"/users": {"get": {}}}}
    import json
    spec_bytes = json.dumps(spec_data).encode("utf-8")

    monkeypatch.setattr(
        "avanamy.services.s3.download_bytes",
        lambda s3_path: spec_bytes,
    )

    result = spec_versions.get_original_spec_for_version(
        spec_id=spec_id,
        version_number=version_number,
        tenant_id=tenant_id,
        db=fake_db,
    )

    assert result["version"] == version_number
    assert result["spec"] == spec_data
    assert "s3_path" in result


def test_get_original_spec_for_version_handles_yaml(monkeypatch):
    """Test that YAML specs are correctly parsed."""
    tenant_id = "tenant-1"
    spec_id = uuid.uuid4()
    version_number = 2
    version_history_id = 456

    fake_db = MagicMock()

    fake_spec = SimpleNamespace(id=spec_id)
    fake_version = SimpleNamespace(id=version_history_id, version=version_number)
    fake_artifact = SimpleNamespace(
        s3_path="tenants/tenant-a/providers/provider-a/api_products/product-a/versions/v2/spec.yaml",
        artifact_type="original_spec",
        version_history_id=version_history_id,
    )

    query_index = {"count": 0}

    def mock_query(model):
        query_index["count"] += 1
        call_num = query_index["count"]

        mock_chain = MagicMock()
        mock_chain.join.return_value = mock_chain
        mock_chain.filter.return_value = mock_chain

        if call_num == 1:
            mock_chain.first.return_value = fake_spec
        elif call_num == 2:
            mock_chain.first.return_value = fake_version
        elif call_num == 3:
            mock_chain.first.return_value = fake_artifact
        else:
            mock_chain.first.return_value = None

        return mock_chain

    fake_db.query.side_effect = mock_query

    # Mock S3 download with YAML content
    yaml_content = """
openapi: 3.0.0
info:
  title: Test API
paths:
  /health:
    get:
      responses:
        '200':
          description: OK
"""
    spec_bytes = yaml_content.encode("utf-8")

    monkeypatch.setattr(
        "avanamy.services.s3.download_bytes",
        lambda s3_path: spec_bytes,
    )

    result = spec_versions.get_original_spec_for_version(
        spec_id=spec_id,
        version_number=version_number,
        tenant_id=tenant_id,
        db=fake_db,
    )

    assert result["version"] == version_number
    assert "openapi" in result["spec"]
    assert result["spec"]["openapi"] == "3.0.0"


def test_get_original_spec_for_version_tenant_not_found(monkeypatch):
    """Test 404 when spec doesn't belong to tenant."""
    fake_db = MagicMock()
    fake_db.query.return_value.join.return_value.join.return_value.filter.return_value.first.return_value = None

    with pytest.raises(HTTPException) as exc:
        spec_versions.get_original_spec_for_version(
            spec_id=uuid.uuid4(),
            version_number=1,
            tenant_id="wrong-tenant",
            db=fake_db,
        )
    assert exc.value.status_code == 404
    assert "API spec not found" in exc.value.detail


def test_get_original_spec_for_version_version_not_found(monkeypatch):
    """Test 404 when version doesn't exist."""
    tenant_id = "tenant-1"
    spec_id = uuid.uuid4()

    fake_db = MagicMock()

    # Spec exists
    fake_spec = SimpleNamespace(id=spec_id)

    query_index = {"count": 0}

    def mock_query(model):
        query_index["count"] += 1
        call_num = query_index["count"]

        mock_chain = MagicMock()
        mock_chain.join.return_value = mock_chain
        mock_chain.filter.return_value = mock_chain

        if call_num == 1:
            mock_chain.first.return_value = fake_spec
        else:
            # Version doesn't exist
            mock_chain.first.return_value = None

        return mock_chain

    fake_db.query.side_effect = mock_query

    with pytest.raises(HTTPException) as exc:
        spec_versions.get_original_spec_for_version(
            spec_id=spec_id,
            version_number=999,
            tenant_id=tenant_id,
            db=fake_db,
        )
    assert exc.value.status_code == 404
    assert "Version not found" in exc.value.detail


def test_get_original_spec_for_version_artifact_not_found(monkeypatch):
    """Test 404 when original_spec artifact doesn't exist for version."""
    tenant_id = "tenant-1"
    spec_id = uuid.uuid4()
    version_number = 5

    fake_db = MagicMock()

    fake_spec = SimpleNamespace(id=spec_id)
    fake_version = SimpleNamespace(id=789, version=version_number)

    query_index = {"count": 0}

    def mock_query(model):
        query_index["count"] += 1
        call_num = query_index["count"]

        mock_chain = MagicMock()
        mock_chain.join.return_value = mock_chain
        mock_chain.filter.return_value = mock_chain

        if call_num == 1:
            mock_chain.first.return_value = fake_spec
        elif call_num == 2:
            mock_chain.first.return_value = fake_version
        else:
            # Artifact doesn't exist
            mock_chain.first.return_value = None

        return mock_chain

    fake_db.query.side_effect = mock_query

    with pytest.raises(HTTPException) as exc:
        spec_versions.get_original_spec_for_version(
            spec_id=spec_id,
            version_number=version_number,
            tenant_id=tenant_id,
            db=fake_db,
        )
    assert exc.value.status_code == 404
    assert "Original spec artifact not found" in exc.value.detail


def test_compare_two_versions_success(monkeypatch):
    """Test successful comparison of two versions."""
    tenant_id = "tenant-1"
    spec_id = uuid.uuid4()
    current_version = 5
    compare_version = 4

    fake_db = MagicMock()

    # Mock spec validation
    fake_spec = SimpleNamespace(id=spec_id)
    fake_db.query.return_value.join.return_value.join.return_value.filter.return_value.first.return_value = fake_spec

    # Mock version history and artifacts for both versions
    fake_version_current = SimpleNamespace(id=501, version=current_version)
    fake_version_compare = SimpleNamespace(id=401, version=compare_version)

    fake_artifact_current = SimpleNamespace(
        s3_path="tenants/t/providers/p/api_products/prod/versions/v5/spec.json",
        artifact_type="original_spec",
        version_history_id=501,
    )
    fake_artifact_compare = SimpleNamespace(
        s3_path="tenants/t/providers/p/api_products/prod/versions/v4/spec.json",
        artifact_type="original_spec",
        version_history_id=401,
    )

    # Set up query chains - will be called multiple times
    query_index = {"count": 0}

    def mock_query(model):
        query_index["count"] += 1
        call_num = query_index["count"]

        mock_chain = MagicMock()
        mock_chain.join.return_value = mock_chain
        mock_chain.filter.return_value = mock_chain

        if call_num == 1:
            # Initial spec validation
            mock_chain.first.return_value = fake_spec
        elif call_num == 2:
            # First version (current)
            mock_chain.first.return_value = fake_version_current
        elif call_num == 3:
            # First artifact (current)
            mock_chain.first.return_value = fake_artifact_current
        elif call_num == 4:
            # Second version (compare)
            mock_chain.first.return_value = fake_version_compare
        elif call_num == 5:
            # Second artifact (compare)
            mock_chain.first.return_value = fake_artifact_compare
        else:
            mock_chain.first.return_value = None

        return mock_chain

    fake_db.query.side_effect = mock_query

    # Mock S3 downloads
    current_spec_data = {"openapi": "3.0.0", "paths": {"/users": {"get": {}, "post": {}}}}
    compare_spec_data = {"openapi": "3.0.0", "paths": {"/users": {"get": {}}}}

    import json
    download_calls = {"count": 0}

    def mock_download(s3_path):
        download_calls["count"] += 1
        if download_calls["count"] == 1:
            return json.dumps(current_spec_data).encode("utf-8")
        else:
            return json.dumps(compare_spec_data).encode("utf-8")

    monkeypatch.setattr(
        "avanamy.services.s3.download_bytes",
        mock_download,
    )

    result = spec_versions.compare_two_versions(
        spec_id=spec_id,
        version_number=current_version,
        compare_with=compare_version,
        tenant_id=tenant_id,
        db=fake_db,
    )

    assert result["current_version"] == current_version
    assert result["previous_version"] == compare_version
    assert result["current_spec"] == current_spec_data
    assert result["previous_spec"] == compare_spec_data


def test_compare_two_versions_current_version_not_found(monkeypatch):
    """Test 404 when current version doesn't exist."""
    tenant_id = "tenant-1"
    spec_id = uuid.uuid4()

    fake_db = MagicMock()

    # Spec exists
    fake_spec = SimpleNamespace(id=spec_id)

    query_index = {"count": 0}

    def mock_query(model):
        query_index["count"] += 1
        call_num = query_index["count"]

        mock_chain = MagicMock()
        mock_chain.join.return_value = mock_chain
        mock_chain.filter.return_value = mock_chain

        if call_num == 1:
            mock_chain.first.return_value = fake_spec
        else:
            # Version doesn't exist
            mock_chain.first.return_value = None

        return mock_chain

    fake_db.query.side_effect = mock_query

    with pytest.raises(HTTPException) as exc:
        spec_versions.compare_two_versions(
            spec_id=spec_id,
            version_number=999,
            compare_with=1,
            tenant_id=tenant_id,
            db=fake_db,
        )
    assert exc.value.status_code == 404
    assert "999" in exc.value.detail


def test_compare_two_versions_compare_version_not_found(monkeypatch):
    """Test 404 when comparison version doesn't exist."""
    tenant_id = "tenant-1"
    spec_id = uuid.uuid4()
    current_version = 5
    compare_version = 999

    fake_db = MagicMock()

    fake_spec = SimpleNamespace(id=spec_id)
    fake_version_current = SimpleNamespace(id=501, version=current_version)
    fake_artifact_current = SimpleNamespace(
        s3_path="tenants/t/providers/p/api_products/prod/versions/v5/spec.json",
        artifact_type="original_spec",
        version_history_id=501,
    )

    current_spec_data = {"openapi": "3.0.0", "paths": {}}

    query_index = {"count": 0}

    def mock_query(model):
        query_index["count"] += 1
        call_num = query_index["count"]

        mock_chain = MagicMock()
        mock_chain.join.return_value = mock_chain
        mock_chain.filter.return_value = mock_chain

        if call_num == 1:
            mock_chain.first.return_value = fake_spec
        elif call_num == 2:
            mock_chain.first.return_value = fake_version_current
        elif call_num == 3:
            mock_chain.first.return_value = fake_artifact_current
        elif call_num == 4:
            # Compare version doesn't exist
            mock_chain.first.return_value = None
        else:
            mock_chain.first.return_value = None

        return mock_chain

    fake_db.query.side_effect = mock_query

    import json
    monkeypatch.setattr(
        "avanamy.services.s3.download_bytes",
        lambda s3_path: json.dumps(current_spec_data).encode("utf-8"),
    )

    with pytest.raises(HTTPException) as exc:
        spec_versions.compare_two_versions(
            spec_id=spec_id,
            version_number=current_version,
            compare_with=compare_version,
            tenant_id=tenant_id,
            db=fake_db,
        )
    assert exc.value.status_code == 404
    assert "999" in exc.value.detail


def test_compare_two_versions_validates_tenant_ownership(monkeypatch):
    """Test that compare endpoint validates tenant ownership."""
    fake_db = MagicMock()
    fake_db.query.return_value.join.return_value.join.return_value.filter.return_value.first.return_value = None

    with pytest.raises(HTTPException) as exc:
        spec_versions.compare_two_versions(
            spec_id=uuid.uuid4(),
            version_number=2,
            compare_with=1,
            tenant_id="wrong-tenant",
            db=fake_db,
        )
    assert exc.value.status_code == 404
    assert "API spec not found" in exc.value.detail