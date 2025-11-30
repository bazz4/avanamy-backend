import json
from unittest.mock import MagicMock, patch

from avanamy.services.api_spec_service import store_api_spec_file


def test_store_api_spec_file_fallback_on_parse_failure():
    """
    If parsing fails (e.g., YAML file but invalid content), the service should:
    - Upload to S3
    - Store a row with parsed_schema=None
    """
    fake_db = MagicMock()

    file_bytes = b"hello"  # invalid for YAML/JSON/XML
    filename = "spec.yaml"

    with patch("avanamy.services.api_spec_service.upload_bytes") as mock_upload, \
         patch("avanamy.services.api_spec_service.ApiSpecRepository") as mock_repo, \
         patch("avanamy.services.api_spec_service.parse_api_spec") as mock_parse:

        mock_upload.return_value = ("some-key", "s3://bucket/some-key")
        mock_parse.side_effect = ValueError("cannot parse")

        fake_spec = MagicMock()
        fake_spec.id = 1
        fake_spec.name = filename
        fake_spec.parsed_schema = None
        fake_spec.original_file_s3_path = "s3://bucket/some-key"

        mock_repo.return_value.create.return_value = fake_spec

        result = store_api_spec_file(
            db=fake_db,
            file_bytes=file_bytes,
            filename=filename,
            content_type="application/yaml",
        )

        mock_upload.assert_called_once()
        mock_repo.return_value.create.assert_called_once()

        # ensure fallback happened
        args, kwargs = mock_repo.return_value.create.call_args
        assert kwargs["parsed_schema"] is None

        assert result is fake_spec


def test_store_api_spec_file_saves_parsed_schema():
    """
    When parsing succeeds, parsed_schema should be stored as JSON string.
    """
    fake_db = MagicMock()

    file_bytes = b'{"name": "x"}'
    filename = "spec.json"

    with patch("avanamy.services.api_spec_service.upload_bytes") as mock_upload, \
         patch("avanamy.services.api_spec_service.ApiSpecRepository") as mock_repo, \
         patch("avanamy.services.api_spec_service.parse_api_spec") as mock_parse:

        mock_upload.return_value = ("key", "s3://bucket/key")
        mock_parse.return_value = {"name": "x"}

        fake_spec = MagicMock()
        fake_spec.id = 10
        fake_spec.name = filename
        fake_spec.parsed_schema = '{"name": "x"}'
        fake_spec.original_file_s3_path = "s3://bucket/key"

        mock_repo.return_value.create.return_value = fake_spec

        result = store_api_spec_file(
            db=fake_db,
            file_bytes=file_bytes,
            filename=filename,
            content_type="application/json",
        )

        mock_repo.return_value.create.assert_called_once()

        # Validate parsed_schema stored as JSON string
        args, kwargs = mock_repo.return_value.create.call_args
        assert json.loads(kwargs["parsed_schema"]) == {"name": "x"}

        assert result is fake_spec


def test_store_api_spec_file_passes_correct_fields():
    """
    Sanity check that all expected fields are passed.
    """
    fake_db = MagicMock()

    file_bytes = b'{"k": 1}'
    filename = "spec.json"

    with patch("avanamy.services.api_spec_service.upload_bytes") as mock_upload, \
         patch("avanamy.services.api_spec_service.ApiSpecRepository") as mock_repo, \
         patch("avanamy.services.api_spec_service.parse_api_spec") as mock_parse:

        mock_upload.return_value = ("abc", "s3://bucket/abc")
        mock_parse.return_value = {"k": 1}

        fake_spec = MagicMock()
        fake_spec.id = 99
        fake_spec.name = filename
        fake_spec.parsed_schema = '{"k": 1}'
        fake_spec.original_file_s3_path = "s3://bucket/abc"

        mock_repo.return_value.create.return_value = fake_spec

        result = store_api_spec_file(
            db=fake_db,
            file_bytes=file_bytes,
            filename=filename,
            content_type="application/json",
        )

        mock_repo.return_value.create.assert_called_once()
        args, kwargs = mock_repo.return_value.create.call_args

        assert kwargs["name"] == filename
        assert kwargs["original_file_s3_path"] == "s3://bucket/abc"

        assert json.loads(kwargs["parsed_schema"]) == {"k": 1}

        assert result is fake_spec
