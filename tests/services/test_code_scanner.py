from avanamy.services.code_scanner import RegexScanner


def test_supports_language():
    scanner = RegexScanner()
    assert scanner.supports_language(".py") is True
    assert scanner.supports_language(".txt") is False


def test_scan_file_detects_endpoints():
    scanner = RegexScanner()
    content = "fetch('/v1/users')\naxios.post(\"/v1/orders\")"

    matches = scanner.scan_file("app.js", content)

    paths = {m.endpoint_path for m in matches}
    methods = {m.http_method for m in matches}

    assert "/v1/users" in paths
    assert "/v1/orders" in paths
    assert "POST" in methods


def test_scan_file_skips_comments():
    scanner = RegexScanner()
    content = "// fetch('/v1/users')"

    matches = scanner.scan_file("app.js", content)
    assert matches == []


def test_scan_file_extracts_full_url():
    scanner = RegexScanner()
    content = "fetch(\"https://api.acme.com/v1/charges\")"

    matches = scanner.scan_file("app.js", content)

    assert any(m.endpoint_path == "/v1/charges" for m in matches)


def test_scan_file_ignores_docs_paths():
    scanner = RegexScanner()
    content = "fetch('/v1/docs')"

    matches = scanner.scan_file("app.js", content)
    assert any(m.endpoint_path == "/v1/docs" for m in matches)
