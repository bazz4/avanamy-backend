import sys
sys.path.insert(0, 'src')

from avanamy.services.code_scanner import RegexScanner

# Test the specific lines that might be missing
test_lines = """
  return apiPost(`/api-specs/${specId}/regenerate-docs`);
  return apiGet(`/docs/${specId}/versions/${versionId}/available`);
  return apiGet(`/docs/${specId}/versions/${versionId}?format=${format}`);
  return apiGet(`/docs/${specId}/latest?format=${format}`);
"""

scanner = RegexScanner()
matches = scanner.scan_file('test.ts', test_lines)

print(f"Found {len(matches)} matches:")
for match in matches:
    print(f"  {match.http_method} {match.endpoint_path} (confidence: {match.confidence})")
    print(f"    Context: {match.code_context}")
