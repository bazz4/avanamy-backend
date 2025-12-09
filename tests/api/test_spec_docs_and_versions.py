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
        SimpleNamespace(version=1, changelog="init", created_at=SimpleNamespace(isoformat=lambda: "ts1")),
        SimpleNamespace(version=2, changelog="second", created_at=SimpleNamespace(isoformat=lambda: "ts2")),
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
