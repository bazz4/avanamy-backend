from fastapi.testclient import TestClient
from avanamy import main as app_main


def test_main_upload_endpoint(monkeypatch):
    # The app's module imports upload_bytes into its namespace; patch that name
    def fake_upload_bytes(arg1, arg2, content_type=None):
        # main.py currently passes a temp path and filename; accept anything
        return "key", "s3://test-bucket/key"

    monkeypatch.setattr(app_main, "upload_bytes", fake_upload_bytes)

    client = TestClient(app_main.app)
    files = {"file": ("hello.txt", b"hello world", "text/plain")}
    resp = client.post("/upload", files=files)

    assert resp.status_code == 200
    data = resp.json()
    assert data["filename"] == "hello.txt"
    assert data["stored_at"].startswith("s3://test-bucket/")
