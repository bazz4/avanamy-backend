# tests/api/test_api_specs_route.py

from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from avanamy.main import app

client = TestClient(app)


def test_upload_api_spec_route():
    fake_spec = MagicMock(
        id=123,
        name="my.yaml",
        version=None,
        description=None,
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
