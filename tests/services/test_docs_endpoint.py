from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch

from avanamy.main import app
from avanamy.repositories.documentation_artifact_repository import (
    DocumentationArtifactRepository,
)
from avanamy.models.documentation_artifact import DocumentationArtifact


client = TestClient(app)


def test_get_docs_not_found(db, monkeypatch):
    def fake_get_latest(self, db, api_spec_id, artifact_type=None):
        return None

    monkeypatch.setattr(
        DocumentationArtifactRepository,
        "get_latest_by_spec_id",
        fake_get_latest,
    )

    resp = client.get("/docs/9999")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Documentation not found"


def test_get_docs_success(db, monkeypatch):
    artifact = DocumentationArtifact(
        id=1,
        api_spec_id=1,
        artifact_type="api_markdown",
        s3_path="docs/1/api.md",
    )

    monkeypatch.setattr(
        DocumentationArtifactRepository,
        "get_latest_by_spec_id",
        lambda self, db, api_spec_id, artifact_type=None: artifact,
    )

    fake_md = b"# Test Doc\nHello!"
    monkeypatch.setattr(
        "avanamy.api.routes.docs.download_bytes",
        lambda key: fake_md,
    )

    resp = client.get("/docs/1")
    assert resp.status_code == 200
    assert resp.text == "# Test Doc\nHello!"
    assert resp.headers["content-type"].startswith("text/markdown")
