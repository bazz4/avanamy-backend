import pytest

from avanamy.services import s3


def test_upload_bytes_success(monkeypatch):
    recorded = {}

    class DummyClient:
        def put_object(self, **kwargs):
            recorded.update(kwargs)
            return {}

    monkeypatch.setattr(s3, "_s3_client", DummyClient())
    monkeypatch.setattr(s3, "AWS_BUCKET", "test-bucket")

    key, url = s3.upload_bytes("path/to/file.txt", b"hello", content_type="text/plain")

    assert key == "path/to/file.txt"
    assert url == "s3://test-bucket/path/to/file.txt"

    assert recorded["Bucket"] == "test-bucket"
    assert recorded["Key"] == "path/to/file.txt"
    assert recorded["Body"] == b"hello"
    assert recorded["ContentType"] == "text/plain"


def test_upload_bytes_no_bucket_raises(monkeypatch):
    monkeypatch.setattr(s3, "AWS_BUCKET", None)
    with pytest.raises(RuntimeError):
        s3.upload_bytes("k", b"data")
