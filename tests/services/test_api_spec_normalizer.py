from avanamy.services.api_spec_normalizer import normalize_api_spec


def test_normalize_simple_dict():
    data = {"Name": " Test ", "Version": "1"}
    out = normalize_api_spec(data)
    assert out["name"] == "Test"
    assert out["version"] == "1"


def test_normalize_nested():
    data = {"Root": {"Inner": " value "}}
    out = normalize_api_spec(data)
    assert out["root"]["inner"] == "value"


def test_normalize_list():
    data = {"items": [" A ", "B "]}
    out = normalize_api_spec(data)
    assert out["items"] == ["A", "B"]


def test_normalize_scalar():
    assert normalize_api_spec("  hi ") == "hi"
    assert normalize_api_spec(123) == 123
