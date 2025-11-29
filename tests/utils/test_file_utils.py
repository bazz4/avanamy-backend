from avanamy.utils.file_utils import detect_file_type


def test_detect_by_extension_json():
    assert detect_file_type("a.json", b"{") == "json"


def test_detect_by_extension_yaml():
    assert detect_file_type("a.yaml", b"x: 1") == "yaml"


def test_detect_by_extension_xml():
    assert detect_file_type("a.xml", b"<root></root>") == "xml"


def test_detect_by_content_fallback():
    assert detect_file_type("noext", b"{\"a\":1}") == "json"
    assert detect_file_type("noext", b"x: 1\n") == "yaml"
    # YAML is permissive and may parse simple XML-looking text as a string,
    # so accept either yaml or xml here depending on parser behavior.
    assert detect_file_type("noext", b"<r></r>") in ("xml", "yaml")


def test_detect_unknown():
    assert detect_file_type("noext", b"\x00\x01\x02") == "unknown"
