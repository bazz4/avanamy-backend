import sys
sys.path.insert(0, 'src')

from avanamy.services.code_scanner import RegexScanner

# Test code that should be found
test_file_content = '''
export async function getProviders(): Promise<Provider[]> {
  return apiGet<Provider[]>('/providers');
}

export async function createProvider(data: ProviderCreate): Promise<Provider> {
  return apiPost<Provider>('/providers', data);
}

export async function deleteProvider(providerId: string): Promise<void> {
  return apiDelete(`/providers/${providerId}`);
}
'''

scanner = RegexScanner()
matches = scanner.scan_file('test.ts', test_file_content)

print(f"Found {len(matches)} matches:")
for match in matches:
    print(f"  {match.http_method} {match.endpoint_path} (confidence: {match.confidence})")
