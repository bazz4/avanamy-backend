from fastapi.testclient import TestClient
from unittest.mock import patch
from types import SimpleNamespace
from avanamy.main import app


def test_upload_api_spec_route():
    fake_spec = SimpleNamespace(
        id=123,
        name="my.yaml",
        version=None,
        description=None,
        original_file_s3_path="s3://test/my.yaml",
    )

    with patch("avanamy.api.routes.api_specs.store_api_spec_file", return_value=fake_spec):
        client = TestClient(app)
        response = client.post(
            "/api-specs/upload",
            files={"file": ("my.yaml", b"content", "application/yaml")},
        )

    assert response.status_code == 200
    data = response.json()

    assert data["id"] == 123
    assert data["name"] == "my.yaml"
    assert data["original_file_s3_path"] == "s3://test/my.yaml"
