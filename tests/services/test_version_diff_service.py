# tests/services/test_version_diff_service.py

import json
import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import pytest

from avanamy.services.version_diff_service import (
    compute_and_store_diff,
    _load_normalized_spec_for_version,
)


@pytest.mark.anyio
async def test_compute_and_store_diff_version_1_no_diff(monkeypatch):
    """Test that version 1 does not compute any diff."""
    spec_id = uuid.uuid4()
    tenant_id = "tenant_test123"
    current_version = 1
    new_normalized_spec = {"openapi": "3.0.0", "paths": {}}

    db = MagicMock()

    # No mocks needed - should return early
    await compute_and_store_diff(
        db,
        spec_id=spec_id,
        tenant_id=tenant_id,
        current_version=current_version,
        new_normalized_spec=new_normalized_spec,
    )

    # DB should not have been accessed for version 1
    db.query.assert_not_called()


@pytest.mark.anyio
async def test_compute_and_store_diff_version_2_computes_diff(monkeypatch):
    """Test that version 2 computes diff against version 1."""
    spec_id = uuid.uuid4()
    tenant_id = "tenant_test123"
    current_version = 2
    previous_version = 1

    previous_normalized_spec = {
        "openapi": "3.0.0",
        "paths": {
            "/users": {"get": {}}
        }
    }

    new_normalized_spec = {
        "openapi": "3.0.0",
        "paths": {
            "/users": {"get": {}, "post": {}}
        }
    }

    diff_result = {
        "breaking": False,
        "changes": [
            {"type": "endpoint_added", "path": "/users", "method": "post"}
        ]
    }

    db = MagicMock()
    version_history = SimpleNamespace(diff=None)

    # Mock _load_normalized_spec_for_version
    monkeypatch.setattr(
        "avanamy.services.version_diff_service._load_normalized_spec_for_version",
        lambda db, spec_id, tenant_id, version: previous_normalized_spec,
    )

    # Mock diff_normalized_specs
    monkeypatch.setattr(
        "avanamy.services.version_diff_service.diff_normalized_specs",
        lambda old_spec, new_spec: diff_result,
    )

    # Mock VersionHistoryRepository.get_by_spec_and_version
    monkeypatch.setattr(
        "avanamy.services.version_diff_service.VersionHistoryRepository.get_by_spec_and_version",
        lambda db, api_spec_id, version: version_history,
    )

    await compute_and_store_diff(
        db,
        spec_id=spec_id,
        tenant_id=tenant_id,
        current_version=current_version,
        new_normalized_spec=new_normalized_spec,
    )

    # Verify diff was stored
    assert version_history.diff == diff_result
    db.commit.assert_called()


@pytest.mark.anyio
async def test_compute_and_store_diff_handles_missing_previous_spec(monkeypatch):
    """Test graceful handling when previous spec cannot be loaded."""
    spec_id = uuid.uuid4()
    tenant_id = "tenant_test123"
    current_version = 5
    new_normalized_spec = {"openapi": "3.0.0", "paths": {}}

    db = MagicMock()

    # Mock _load_normalized_spec_for_version to return None
    monkeypatch.setattr(
        "avanamy.services.version_diff_service._load_normalized_spec_for_version",
        lambda db, spec_id, tenant_id, version: None,
    )

    # Should not raise an exception
    await compute_and_store_diff(
        db,
        spec_id=spec_id,
        tenant_id=tenant_id,
        current_version=current_version,
        new_normalized_spec=new_normalized_spec,
    )

    # DB commit should not be called since we couldn't compute diff
    db.commit.assert_not_called()


@pytest.mark.anyio
async def test_compute_and_store_diff_handles_diff_computation_error(monkeypatch):
    """Test graceful handling when diff computation fails."""
    spec_id = uuid.uuid4()
    tenant_id = "tenant_test123"
    current_version = 3

    previous_normalized_spec = {"openapi": "3.0.0", "paths": {}}
    new_normalized_spec = {"openapi": "3.0.0", "paths": {}}

    db = MagicMock()

    # Mock _load_normalized_spec_for_version
    monkeypatch.setattr(
        "avanamy.services.version_diff_service._load_normalized_spec_for_version",
        lambda db, spec_id, tenant_id, version: previous_normalized_spec,
    )

    # Mock diff_normalized_specs to raise exception
    monkeypatch.setattr(
        "avanamy.services.version_diff_service.diff_normalized_specs",
        MagicMock(side_effect=Exception("Diff computation failed")),
    )

    # Should not raise an exception
    await compute_and_store_diff(
        db,
        spec_id=spec_id,
        tenant_id=tenant_id,
        current_version=current_version,
        new_normalized_spec=new_normalized_spec,
    )

    # DB commit should not be called since diff computation failed
    db.commit.assert_not_called()


@pytest.mark.anyio
async def test_compute_and_store_diff_handles_version_history_not_found(monkeypatch):
    """Test graceful handling when VersionHistory record is not found."""
    spec_id = uuid.uuid4()
    tenant_id = "tenant_test123"
    current_version = 4

    previous_normalized_spec = {"openapi": "3.0.0", "paths": {}}
    new_normalized_spec = {"openapi": "3.0.0", "paths": {}}
    diff_result = {"breaking": False, "changes": []}

    db = MagicMock()

    # Mock _load_normalized_spec_for_version
    monkeypatch.setattr(
        "avanamy.services.version_diff_service._load_normalized_spec_for_version",
        lambda db, spec_id, tenant_id, version: previous_normalized_spec,
    )

    # Mock diff_normalized_specs
    monkeypatch.setattr(
        "avanamy.services.version_diff_service.diff_normalized_specs",
        lambda old_spec, new_spec: diff_result,
    )

    # Mock VersionHistoryRepository.get_by_spec_and_version to return None
    monkeypatch.setattr(
        "avanamy.services.version_diff_service.VersionHistoryRepository.get_by_spec_and_version",
        lambda db, api_spec_id, version: None,
    )

    # Should not raise an exception
    await compute_and_store_diff(
        db,
        spec_id=spec_id,
        tenant_id=tenant_id,
        current_version=current_version,
        new_normalized_spec=new_normalized_spec,
    )

    # DB commit should not be called
    db.commit.assert_not_called()


def test_load_normalized_spec_for_version_success(monkeypatch):
    """Test successful loading of normalized spec from S3."""
    spec_id = uuid.uuid4()
    tenant_id = "tenant_test123"
    version = 3
    version_history_id = 123

    normalized_spec = {
        "openapi": "3.0.0",
        "paths": {
            "/users": {"get": {}}
        }
    }

    normalized_json = json.dumps(normalized_spec)
    normalized_bytes = normalized_json.encode("utf-8")

    version_history = SimpleNamespace(id=version_history_id, version=version)
    artifact = SimpleNamespace(
        s3_path="tenants/tenant-a/providers/provider-a/api_products/product-a/versions/v3/normalized.json",
        artifact_type="normalized_spec",
        version_history_id=version_history_id
    )

    # Mock DB queries
    class MockQuery:
        def __init__(self, result):
            self.result = result

        def filter(self, *args, **kwargs):
            return self

        def first(self):
            return self.result

    db = MagicMock()

    def query_side_effect(model):
        model_name = getattr(model, "__name__", str(model))
        if "VersionHistory" in model_name:
            return MockQuery(version_history)
        elif "DocumentationArtifact" in model_name:
            return MockQuery(artifact)
        return MockQuery(None)

    db.query.side_effect = query_side_effect

    # Mock S3 download
    monkeypatch.setattr(
        "avanamy.services.version_diff_service.download_bytes",
        lambda s3_path: normalized_bytes,
    )

    result = _load_normalized_spec_for_version(
        db,
        spec_id=spec_id,
        tenant_id=tenant_id,
        version=version,
    )

    assert result == normalized_spec


def test_load_normalized_spec_for_version_handles_missing_version_history():
    """Test handling when VersionHistory record doesn't exist."""
    spec_id = uuid.uuid4()
    tenant_id = "tenant_test123"
    version = 10

    class MockQuery:
        def filter(self, *args, **kwargs):
            return self

        def first(self):
            return None

    db = MagicMock()
    db.query.return_value = MockQuery()

    result = _load_normalized_spec_for_version(
        db,
        spec_id=spec_id,
        tenant_id=tenant_id,
        version=version,
    )

    assert result is None


def test_load_normalized_spec_for_version_handles_missing_artifact():
    """Test handling when normalized_spec artifact doesn't exist for a version."""
    spec_id = uuid.uuid4()
    tenant_id = "tenant_test123"
    version = 5
    version_history_id = 456

    version_history = SimpleNamespace(id=version_history_id, version=version)

    class MockQuery:
        def __init__(self, result):
            self.result = result

        def filter(self, *args, **kwargs):
            return self

        def first(self):
            return self.result

    db = MagicMock()

    def query_side_effect(model):
        model_name = getattr(model, "__name__", str(model))
        if "VersionHistory" in model_name:
            return MockQuery(version_history)
        elif "DocumentationArtifact" in model_name:
            return MockQuery(None)  # No artifact found
        return MockQuery(None)

    db.query.side_effect = query_side_effect

    result = _load_normalized_spec_for_version(
        db,
        spec_id=spec_id,
        tenant_id=tenant_id,
        version=version,
    )

    assert result is None


def test_load_normalized_spec_for_version_handles_s3_download_error(monkeypatch):
    """Test handling when S3 download fails."""
    spec_id = uuid.uuid4()
    tenant_id = "tenant_test123"
    version = 2
    version_history_id = 789

    version_history = SimpleNamespace(id=version_history_id, version=version)
    artifact = SimpleNamespace(
        s3_path="tenants/tenant-a/providers/provider-a/api_products/product-a/versions/v2/normalized.json",
        artifact_type="normalized_spec",
        version_history_id=version_history_id
    )

    class MockQuery:
        def __init__(self, result):
            self.result = result

        def filter(self, *args, **kwargs):
            return self

        def first(self):
            return self.result

    db = MagicMock()

    def query_side_effect(model):
        model_name = getattr(model, "__name__", str(model))
        if "VersionHistory" in model_name:
            return MockQuery(version_history)
        elif "DocumentationArtifact" in model_name:
            return MockQuery(artifact)
        return MockQuery(None)

    db.query.side_effect = query_side_effect

    # Mock S3 download to raise exception
    monkeypatch.setattr(
        "avanamy.services.version_diff_service.download_bytes",
        MagicMock(side_effect=Exception("S3 download failed")),
    )

    result = _load_normalized_spec_for_version(
        db,
        spec_id=spec_id,
        tenant_id=tenant_id,
        version=version,
    )

    assert result is None


def test_load_normalized_spec_for_version_with_version_gaps():
    """
    Test that the function correctly handles version gaps.

    For example, if versions 1-7 are missing but version 17 exists,
    it should find version 17 by the FK relationship, not by counting.
    """
    spec_id = uuid.uuid4()
    tenant_id = "tenant_test123"
    version = 17  # Version 17 exists, but 1-16 might be missing
    version_history_id = 9999

    normalized_spec = {"openapi": "3.0.0", "paths": {"/health": {"get": {}}}}
    normalized_json = json.dumps(normalized_spec)
    normalized_bytes = normalized_json.encode("utf-8")

    version_history = SimpleNamespace(id=version_history_id, version=version)
    artifact = SimpleNamespace(
        s3_path="tenants/tenant-a/providers/provider-a/api_products/product-a/versions/v17/normalized.json",
        artifact_type="normalized_spec",
        version_history_id=version_history_id
    )

    class MockQuery:
        def __init__(self, result):
            self.result = result

        def filter(self, *args, **kwargs):
            return self

        def first(self):
            return self.result

    db = MagicMock()

    def query_side_effect(model):
        model_name = getattr(model, "__name__", str(model))
        if "VersionHistory" in model_name:
            return MockQuery(version_history)
        elif "DocumentationArtifact" in model_name:
            # The query filters by version_history_id, not by artifact count
            # This is the key fix - it should find the artifact by FK relationship
            return MockQuery(artifact)
        return MockQuery(None)

    db.query.side_effect = query_side_effect

    # Mock download_bytes
    def mock_download(s3_path):
        return normalized_bytes

    import avanamy.services.version_diff_service as vds
    original_download = vds.download_bytes
    vds.download_bytes = mock_download

    try:
        result = _load_normalized_spec_for_version(
            db,
            spec_id=spec_id,
            tenant_id=tenant_id,
            version=version,
        )

        # The spec should be found correctly by FK relationship
        assert result == normalized_spec
    finally:
        vds.download_bytes = original_download


def test_load_normalized_spec_for_version_handles_invalid_json(monkeypatch):
    """Test handling when downloaded spec is not valid JSON."""
    spec_id = uuid.uuid4()
    tenant_id = "tenant_test123"
    version = 4
    version_history_id = 555

    version_history = SimpleNamespace(id=version_history_id, version=version)
    artifact = SimpleNamespace(
        s3_path="tenants/tenant-a/providers/provider-a/api_products/product-a/versions/v4/normalized.json",
        artifact_type="normalized_spec",
        version_history_id=version_history_id
    )

    class MockQuery:
        def __init__(self, result):
            self.result = result

        def filter(self, *args, **kwargs):
            return self

        def first(self):
            return self.result

    db = MagicMock()

    def query_side_effect(model):
        model_name = getattr(model, "__name__", str(model))
        if "VersionHistory" in model_name:
            return MockQuery(version_history)
        elif "DocumentationArtifact" in model_name:
            return MockQuery(artifact)
        return MockQuery(None)

    db.query.side_effect = query_side_effect

    # Mock S3 download to return invalid JSON
    monkeypatch.setattr(
        "avanamy.services.version_diff_service.download_bytes",
        lambda s3_path: b"not valid json{{{",
    )

    result = _load_normalized_spec_for_version(
        db,
        spec_id=spec_id,
        tenant_id=tenant_id,
        version=version,
    )

    assert result is None


@pytest.mark.anyio
async def test_compute_and_store_diff_includes_breaking_changes(monkeypatch):
    """Test that breaking changes are correctly identified and stored."""
    spec_id = uuid.uuid4()
    tenant_id = "tenant_test123"
    current_version = 3

    previous_normalized_spec = {
        "openapi": "3.0.0",
        "paths": {
            "/users": {"get": {}, "delete": {}}
        }
    }

    new_normalized_spec = {
        "openapi": "3.0.0",
        "paths": {
            "/users": {"get": {}}  # DELETE endpoint removed - BREAKING
        }
    }

    diff_result = {
        "breaking": True,
        "changes": [
            {"type": "endpoint_removed", "path": "/users", "method": "delete"}
        ]
    }

    db = MagicMock()
    version_history = SimpleNamespace(diff=None, id=123)

    # Mock impact analysis result
    mock_impact_result = SimpleNamespace(
        has_impact=True,
        total_affected_repos=2,
        total_usages_affected=5
    )

    # Mock ImpactAnalysisService
    async def mock_analyze_breaking_changes(tenant_id, diff, spec_id, version_history_id, created_by_user_id):
        return mock_impact_result

    mock_impact_service = MagicMock()
    mock_impact_service.analyze_breaking_changes = mock_analyze_breaking_changes

    monkeypatch.setattr(
        "avanamy.services.version_diff_service.ImpactAnalysisService",
        lambda db: mock_impact_service,
    )

    monkeypatch.setattr(
        "avanamy.services.version_diff_service._load_normalized_spec_for_version",
        lambda db, spec_id, tenant_id, version: previous_normalized_spec,
    )

    monkeypatch.setattr(
        "avanamy.services.version_diff_service.diff_normalized_specs",
        lambda old_spec, new_spec: diff_result,
    )

    monkeypatch.setattr(
        "avanamy.services.version_diff_service.VersionHistoryRepository.get_by_spec_and_version",
        lambda db, api_spec_id, version: version_history,
    )

    await compute_and_store_diff(
        db,
        spec_id=spec_id,
        tenant_id=tenant_id,
        current_version=current_version,
        new_normalized_spec=new_normalized_spec,
    )

    # Verify diff includes breaking flag
    assert version_history.diff == diff_result
    assert version_history.diff["breaking"] is True
    db.commit.assert_called()
