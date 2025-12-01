# tests/api/test_api_specs_route.py

import json
from fastapi.testclient import TestClient
from unittest.mock import patch
from types import SimpleNamespace
from avanamy.main import app
from avanamy.models.api_spec import ApiSpec

client = TestClient(app)

def test_upload_api_spec_route():
    fake_spec = SimpleNamespace(
        id=123,
        name="my.yaml",
        version=None,
        description=None,
        parsed_schema={},
        original_file_s3_path="s3://test/my.yaml",
    )

    # Mock the service layer
    with patch("avanamy.api.routes.api_specs.store_api_spec_file", return_value=fake_spec):
        response = client.post(
            "/api-specs/upload",
            files={"file": ("my.yaml", b"content", "application/yaml")},
        )

    assert response.status_code == 200
    data = response.json()

    assert data["id"] == 123
    assert data["name"] == "my.yaml"
    assert data["original_file_s3_path"] == "s3://test/my.yaml"

def test_regenerate_docs_endpoint_success(client, db, monkeypatch):
    class FakeSpec:
        id = 7
        parsed_schema = "{}"

    monkeypatch.setattr(
        "avanamy.api.routes.api_specs.ApiSpecRepository.get_by_id",
        lambda db, spec_id: FakeSpec()
    )

    monkeypatch.setattr(
        "avanamy.api.routes.api_specs.regenerate_all_docs_for_spec",
        lambda db, spec: ("docs/7/api.md", "docs/7/api.html")
    )

    resp = client.post("/api-specs/7/regenerate-docs")
    assert resp.status_code == 200

    body = resp.json()
    assert body["spec_id"] == 7
    assert body["markdown_s3_path"] == "docs/7/api.md"
    assert body["html_s3_path"] == "docs/7/api.html"

def test_regenerate_docs_endpoint_not_found(client, monkeypatch):
    monkeypatch.setattr(
        "avanamy.api.routes.api_specs.ApiSpecRepository.get_by_id",
        lambda db, spec_id: None
    )

    resp = client.post("/api-specs/999/regenerate-docs")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "API spec not found"
