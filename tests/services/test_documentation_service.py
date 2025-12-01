# tests/services/test_documentation_service.py
import json
from unittest.mock import MagicMock, patch

from avanamy.services.documentation_service import (
    generate_and_store_markdown_for_spec,
    regenerate_all_docs_for_spec,
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

        # Correct markdown key
        assert key == "docs/123/api.md"

        # Called twice: markdown and html
        assert mock_upload.call_count == 2
        mock_upload.assert_any_call(
            "docs/123/api.md",
            mock_upload.call_args_list[0][0][1],  # markdown bytes
            content_type="text/markdown",
        )
        mock_upload.assert_any_call(
            "docs/123/api.html",
            mock_upload.call_args_list[1][0][1],  # html bytes
            content_type="text/html",
        )

        # Verify DB artifact creation for markdown
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

def test_regenerate_all_docs_success(db):
    spec = ApiSpec(
        id=42,
        name="Test",
        version="1.0",
        parsed_schema=json.dumps({
            "info": {"title": "X"},
            "paths": {},
            "components": {},
        }),
        original_file_s3_path="s3://something",
    )

    mock_upload = MagicMock(return_value=("etag", "s3://fake"))
    mock_repo = MagicMock()

    with patch("avanamy.services.documentation_service.upload_bytes", mock_upload), \
         patch("avanamy.services.documentation_service.DocumentationArtifactRepository", MagicMock(return_value=mock_repo)), \
         patch("avanamy.services.documentation_service.generate_markdown_from_normalized_spec", return_value="# MD"), \
         patch("avanamy.services.documentation_service.render_markdown_to_html", return_value="<html>X</html>"):

        md_key, html_key = regenerate_all_docs_for_spec(db, spec)

        assert md_key == "docs/42/api.md"
        assert html_key == "docs/42/api.html"

        assert mock_upload.call_count == 2
        assert mock_repo.create.call_count == 2

        first_call = mock_repo.create.call_args_list[0]
        assert first_call.kwargs["artifact_type"] == "api_markdown"
        assert first_call.kwargs["s3_path"] == "docs/42/api.md"

        second_call = mock_repo.create.call_args_list[1]
        assert second_call.kwargs["artifact_type"] == "api_html"
        assert second_call.kwargs["s3_path"] == "docs/42/api.html"
