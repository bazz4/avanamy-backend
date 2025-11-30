import json
from unittest.mock import MagicMock, patch

from avanamy.services.documentation_service import (
    generate_and_store_markdown_for_spec,
    ARTIFACT_TYPE_API_MARKDOWN,
)
from avanamy.models.api_spec import ApiSpec


def test_generate_and_store_markdown_for_spec_success(db):
    test_spec = ApiSpec(
        id=123,
        name="Test",
        version="1.0",
        description="",
        original_file_s3_path="s3://test",
        parsed_schema=json.dumps({
            "info": {"title": "Hello", "version": "1.0"},
            "paths": {},
            "components": {},
        }),
    )

    mock_upload = MagicMock(return_value=("etag", "s3://fakeurl"))
    mock_repo = MagicMock()

    with patch("avanamy.services.documentation_service.upload_bytes", mock_upload), \
         patch("avanamy.services.documentation_service.DocumentationArtifactRepository", MagicMock(return_value=mock_repo)):

        key = generate_and_store_markdown_for_spec(db, test_spec)

        assert key == "docs/123/api.md"
        mock_upload.assert_called_once()
        mock_repo.create.assert_called_once_with(
            db,
            api_spec_id=123,
            artifact_type=ARTIFACT_TYPE_API_MARKDOWN,
            s3_path="docs/123/api.md",
        )


def test_generate_and_store_markdown_returns_none_if_schema_missing(db):
    spec = ApiSpec(
        id=5,
        name="x",
        version="0.1",
        parsed_schema=None,
        original_file_s3_path="s3://x",
    )

    assert generate_and_store_markdown_for_spec(db, spec) is None
