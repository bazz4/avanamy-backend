from avanamy.services.api_spec_parser import parse_api_spec


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
    import pytest

    with pytest.raises(ValueError):
        parse_api_spec("unknown.bin", data)
