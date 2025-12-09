from types import SimpleNamespace
from unittest.mock import MagicMock

from avanamy.repositories.documentation_artifact_repository import DocumentationArtifactRepository


def test_create_artifact_saves_and_refreshes():
    fake_db = MagicMock()
    fake_db.add = MagicMock()
    fake_db.commit = MagicMock()
    fake_db.refresh = MagicMock()

    artifact = DocumentationArtifactRepository.create(
        fake_db,
        tenant_id="tenant-1",
        api_spec_id="spec-1",
        artifact_type="markdown",
        s3_path="s3://output.md",
    )

    fake_db.add.assert_called_once()
    fake_db.commit.assert_called_once()
    fake_db.refresh.assert_called_once_with(artifact)
    assert artifact.artifact_type == "markdown"
    assert artifact.tenant_id == "tenant-1"


def test_list_and_get_latest_artifacts_for_spec():
    fake_db = MagicMock()
    fake_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = ["a", "b"]
    fake_db.query.return_value.filter.return_value.order_by.return_value.first.return_value = SimpleNamespace(
        s3_path="latest"
    )

    artifacts = DocumentationArtifactRepository.list_for_spec(fake_db, "spec-1", "tenant-1")
    assert artifacts == ["a", "b"]

    latest = DocumentationArtifactRepository.get_latest(
        fake_db,
        api_spec_id="spec-1",
        tenant_id="tenant-1",
        artifact_type="md",
    )
    assert latest.s3_path == "latest"
