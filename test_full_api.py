import sys
sys.path.insert(0, 'src')

from avanamy.services.code_scanner import RegexScanner

# Read the actual frontend API file
api_file_path = r'..\avanamy-dashboard\src\lib\api.ts'

with open(api_file_path, 'r', encoding='utf-8') as f:
    file_content = f.read()

scanner = RegexScanner()
matches = scanner.scan_file('src/lib/api.ts', file_content)

print(f"Found {len(matches)} matches in api.ts:\n")

# Group by HTTP method
by_method = {}
for match in matches:
    method = match.http_method or 'UNKNOWN'
    if method not in by_method:
        by_method[method] = []
    by_method[method].append(match)

# Print summary
for method in sorted(by_method.keys()):
    print(f"{method}: {len(by_method[method])} endpoints")

print("\nDetailed matches:")
for match in sorted(matches, key=lambda m: m.line_number):
    print(f"  Line {match.line_number:3d}: {match.http_method or 'N/A':6s} {match.endpoint_path}")
