# tests/services/test_original_spec_artifact_service.py

import uuid
from unittest.mock import MagicMock, patch
import pytest

from avanamy.services.original_spec_artifact_service import store_original_spec_artifact


def test_store_original_spec_artifact_creates_artifact_with_correct_type(monkeypatch):
    """Test that store_original_spec_artifact creates artifact with artifact_type='original_spec'."""
    tenant_id = uuid.uuid4()
    api_spec_id = uuid.uuid4()
    version_history_id = 1
    s3_path = "tenants/tenant-a/providers/provider-a/api_products/product-a/versions/v1/spec.json"

    db = MagicMock()
    create_mock = MagicMock()

    # Mock the DocumentationArtifactRepository
    mock_repo = MagicMock()
    mock_repo.create = create_mock

    monkeypatch.setattr(
        "avanamy.services.original_spec_artifact_service.DocumentationArtifactRepository",
        lambda: mock_repo,
    )

    # Call the service
    store_original_spec_artifact(
        db,
        tenant_id=tenant_id,
        api_spec_id=api_spec_id,
        version_history_id=version_history_id,
        s3_path=s3_path,
    )

    # Verify repository.create was called once
    create_mock.assert_called_once()

    # Verify the call arguments
    kwargs = create_mock.call_args.kwargs
    assert kwargs["db"] == db
    assert kwargs["tenant_id"] == str(tenant_id)
    assert kwargs["api_spec_id"] == str(api_spec_id)
    assert kwargs["artifact_type"] == "original_spec"
    assert kwargs["s3_path"] == s3_path
    assert kwargs["version_history_id"] == version_history_id


def test_store_original_spec_artifact_links_to_version_history(monkeypatch):
    """Test that the artifact is correctly linked to version_history_id."""
    tenant_id = uuid.uuid4()
    api_spec_id = uuid.uuid4()
    version_history_id = 5  # Not version 1 to test non-initial versions
    s3_path = "tenants/tenant-a/providers/provider-a/api_products/product-a/versions/v5/spec.yaml"

    db = MagicMock()
    create_mock = MagicMock()

    mock_repo = MagicMock()
    mock_repo.create = create_mock

    monkeypatch.setattr(
        "avanamy.services.original_spec_artifact_service.DocumentationArtifactRepository",
        lambda: mock_repo,
    )

    store_original_spec_artifact(
        db,
        tenant_id=tenant_id,
        api_spec_id=api_spec_id,
        version_history_id=version_history_id,
        s3_path=s3_path,
    )

    kwargs = create_mock.call_args.kwargs
    assert kwargs["version_history_id"] == version_history_id


def test_store_original_spec_artifact_stores_correct_s3_path(monkeypatch):
    """Test that the S3 path is stored correctly in the artifact."""
    tenant_id = uuid.uuid4()
    api_spec_id = uuid.uuid4()
    version_history_id = 2
    s3_path = "tenants/custom-tenant/providers/custom-provider/api_products/custom-product/versions/v2/openapi.json"

    db = MagicMock()
    create_mock = MagicMock()

    mock_repo = MagicMock()
    mock_repo.create = create_mock

    monkeypatch.setattr(
        "avanamy.services.original_spec_artifact_service.DocumentationArtifactRepository",
        lambda: mock_repo,
    )

    store_original_spec_artifact(
        db,
        tenant_id=tenant_id,
        api_spec_id=api_spec_id,
        version_history_id=version_history_id,
        s3_path=s3_path,
    )

    kwargs = create_mock.call_args.kwargs
    assert kwargs["s3_path"] == s3_path


def test_store_original_spec_artifact_handles_error_gracefully(monkeypatch):
    """Test that errors during artifact creation are propagated."""
    tenant_id = uuid.uuid4()
    api_spec_id = uuid.uuid4()
    version_history_id = 1
    s3_path = "tenants/tenant-a/providers/provider-a/api_products/product-a/versions/v1/spec.json"

    db = MagicMock()

    # Mock repository to raise an exception
    mock_repo = MagicMock()
    mock_repo.create.side_effect = Exception("Database error")

    monkeypatch.setattr(
        "avanamy.services.original_spec_artifact_service.DocumentationArtifactRepository",
        lambda: mock_repo,
    )

    # Verify that the exception is raised
    with pytest.raises(Exception) as exc_info:
        store_original_spec_artifact(
            db,
            tenant_id=tenant_id,
            api_spec_id=api_spec_id,
            version_history_id=version_history_id,
            s3_path=s3_path,
        )

    assert "Database error" in str(exc_info.value)


def test_store_original_spec_artifact_converts_uuids_to_strings(monkeypatch):
    """Test that UUID parameters are correctly converted to strings for the repository."""
    tenant_id = uuid.uuid4()
    api_spec_id = uuid.uuid4()
    version_history_id = 3
    s3_path = "tenants/tenant-a/providers/provider-a/api_products/product-a/versions/v3/spec.json"

    db = MagicMock()
    create_mock = MagicMock()

    mock_repo = MagicMock()
    mock_repo.create = create_mock

    monkeypatch.setattr(
        "avanamy.services.original_spec_artifact_service.DocumentationArtifactRepository",
        lambda: mock_repo,
    )

    store_original_spec_artifact(
        db,
        tenant_id=tenant_id,
        api_spec_id=api_spec_id,
        version_history_id=version_history_id,
        s3_path=s3_path,
    )

    kwargs = create_mock.call_args.kwargs
    # Verify UUIDs are converted to strings
    assert isinstance(kwargs["tenant_id"], str)
    assert isinstance(kwargs["api_spec_id"], str)
    assert kwargs["tenant_id"] == str(tenant_id)
    assert kwargs["api_spec_id"] == str(api_spec_id)
