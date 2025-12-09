from fastapi.testclient import TestClient
from avanamy import main as app_main


def test_health_endpoint():
    client = TestClient(app_main.app)
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}

