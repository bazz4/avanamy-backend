# tests/services/test_api_spec_service.py

from unittest.mock import MagicMock, patch
from avanamy.services.api_spec_service import store_api_spec_file


def test_store_api_spec_file_creates_s3_and_db_record():
    fake_db = MagicMock()

    file_bytes = b"hello"
    filename = "spec.yaml"

    with patch("avanamy.services.api_spec_service.upload_bytes") as mock_upload, \
         patch("avanamy.services.api_spec_service.ApiSpecRepository") as mock_repo:

        mock_upload.return_value = ("some-key", "s3://bucket/some-key")

        # Correctly mock the spec instance
        fake_spec = MagicMock()
        fake_spec.id = 1
        fake_spec.name = "spec.yaml"
        fake_spec.version = None
        fake_spec.description = None
        fake_spec.original_file_s3_path = "s3://bucket/some-key"
        fake_spec.parsed_schema = None

        mock_repo.create.return_value = fake_spec

        result = store_api_spec_file(
            db=fake_db,
            file_bytes=file_bytes,
            filename=filename,
            content_type="application/yaml",
        )

        # Assertions
        mock_upload.assert_called_once()
        mock_repo.create.assert_called_once()

        assert result.id == 1
        assert result.name == "spec.yaml"
        assert result.original_file_s3_path == "s3://bucket/some-key"
