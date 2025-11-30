from fastapi.testclient import TestClient
from unittest.mock import patch

from avanamy.main import app
from avanamy.services.api_spec_service import store_api_spec_file


client = TestClient(app)


def test_api_spec_upload_generates_docs(monkeypatch, db):

    # -------------------------------------------------------
    # Patch the documentation generator so no S3 is touched
    # -------------------------------------------------------
    mock_docgen = patch(
        "avanamy.services.api_spec_service.generate_and_store_markdown_for_spec"
    ).start()

    # -------------------------------------------------------
    # Patch S3 upload so raw spec upload doesn't hit AWS
    # -------------------------------------------------------
    mock_upload = patch(
        "avanamy.services.api_spec_service.upload_bytes",
        return_value=("etag", "s3://test/spec.json"),
    ).start()

    # Minimal valid OpenAPI spec as upload
    content = b'{"openapi": "3.0.0", "info": {"title": "X"}, "paths": {}}'

    response = client.post(
        "/api-specs/upload",
        files={"file": ("spec.json", content, "application/json")},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "spec.json" or data["name"] == "spec"

    # Assert documentation generator was invoked
    mock_docgen.assert_called_once()

    patch.stopall()
