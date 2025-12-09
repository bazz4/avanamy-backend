import pytest
from fastapi import HTTPException
from types import SimpleNamespace
from unittest.mock import MagicMock

from avanamy.repositories.documentation_artifact_repository import (
    DocumentationArtifactRepository,
)
from avanamy.api.routes import docs as docs_route
from avanamy.models.documentation_artifact import DocumentationArtifact


def test_get_docs_not_found(monkeypatch):
    fake_db = MagicMock()
    monkeypatch.setattr(
        DocumentationArtifactRepository,
        "get_latest_by_spec_id",
        lambda self, db, api_spec_id, tenant_id=None, artifact_type=None: None,
        raising=False,
    )

    with pytest.raises(HTTPException) as exc:
        docs_route.get_original_spec(spec_id=1, tenant_id="tenant-x", db=fake_db)
    assert exc.value.status_code == 404
    assert exc.value.detail == "Documentation not found"


def test_get_docs_success(monkeypatch):
    fake_db = MagicMock()
    artifact = DocumentationArtifact(
        id=1,
        api_spec_id=1,
        artifact_type="api_markdown",
        s3_path="docs/1/api.md",
        tenant_id="tenant-x",
    )

    monkeypatch.setattr(
        DocumentationArtifactRepository,
        "get_latest_by_spec_id",
        lambda self, db, api_spec_id, tenant_id=None, artifact_type=None: artifact,
        raising=False,
    )

    fake_md = b"# Test Doc\nHello!"
    monkeypatch.setattr(
        "avanamy.api.routes.docs.download_bytes",
        lambda key: fake_md,
    )

    resp = docs_route.get_original_spec(spec_id=1, tenant_id="tenant-x", db=fake_db)
    assert resp.status_code == 200
    assert resp.body.decode("utf-8") == "# Test Doc\nHello!"
