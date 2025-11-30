import json
import pytest
from avanamy.db.database import SessionLocal
from avanamy.services.api_spec_parser import parse_api_spec
from avanamy.models.api_spec import ApiSpec
from fastapi.testclient import TestClient
from avanamy.main import app

client = TestClient(app)

def test_parse_json():
    data = b'{"name": "test", "version": "1.0"}'
    out = parse_api_spec("spec.json", data)
    assert isinstance(out, dict)
    assert out["name"] == "test"


def test_parse_yaml():
    data = b"name: test\nversion: 1.0\n"
    out = parse_api_spec("spec.yaml", data)
    assert isinstance(out, dict)
    assert out["name"] == "test"


def test_parse_xml():
    data = b"<root><child>value</child></root>"
    out = parse_api_spec("spec.xml", data)
    # xml parser returns {'child': ['value']} for this structure
    assert isinstance(out, dict)
    assert "child" in out
    assert out["child"][0] == "value"


def test_parse_unknown_raises():
    # Use non-decodable bytes so detection falls back to 'unknown'
    data = b"\x00\x01\x02"

    with pytest.raises(ValueError):
        parse_api_spec("unknown.bin", data)

def test_upload_stores_parsed_schema():
    data = '{"a": 1}'
    response = client.post(
        "/api-specs/upload",
        files={"file": ("spec.json", data, "application/json")},
    )

    assert response.status_code == 200
    spec_id = response.json()["id"]

    db = SessionLocal()
    record = get_spec(db, spec_id)

    raw = record["parsed_schema"]
    # Be tolerant: some DB backends / model mappings may return a dict
    # while others return a JSON string. Handle both.
    if isinstance(raw, dict):
        parsed = raw
    elif raw is None:
        parsed = None
    else:
        parsed = json.loads(raw)

    assert parsed["a"] == 1


def get_spec(db, spec_id):
    # Query the ApiSpec model for the given id and return a dict-like record
    record = db.query(ApiSpec).filter(ApiSpec.id == spec_id).first()
    if record is None:
        raise ValueError(f"Spec with id {spec_id} not found")
    # Ensure we return a mapping with "parsed_schema" as the tests expect
    return {"parsed_schema": record.parsed_schema}
