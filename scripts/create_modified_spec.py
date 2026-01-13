#!/usr/bin/env python3
"""
Download Open-Meteo spec, identify real endpoints, and create modified version
"""

import requests
import yaml
from pathlib import Path

# Download original spec
print("📥 Downloading original Open-Meteo spec...")
response = requests.get("https://raw.githubusercontent.com/open-meteo/open-meteo/main/openapi.yml")
response.raise_for_status()

spec = yaml.safe_load(response.text)

# Save original
original_path = Path("openmeteo-original.yml")
with open(original_path, "w", encoding='utf-8') as f:
    yaml.dump(spec, f, default_flow_style=False, sort_keys=False)
print(f"✅ Saved original spec to {original_path}")

# List all endpoints
print("\n📋 Endpoints in original spec:")
if 'paths' in spec:
    for i, path in enumerate(spec['paths'].keys(), 1):
        methods = list(spec['paths'][path].keys())
        print(f"   {i}. {path} ({', '.join(methods)})")

# Choose endpoint to remove (use first one)
if 'paths' in spec and len(spec['paths']) > 0:
    endpoint_to_remove = list(spec['paths'].keys())[0]
    print(f"\n🎯 Will remove: {endpoint_to_remove}")
    
    # Create modified version
    modified_spec = spec.copy()
    del modified_spec['paths'][endpoint_to_remove]
    
    # Update version
    if 'info' in modified_spec:
        old_version = modified_spec['info'].get('version', '1.0.0')
        modified_spec['info']['version'] = '2.0.0-modified'
        modified_spec['info']['description'] = modified_spec['info'].get('description', '') + f'\n\n**Modified for testing**: Removed {endpoint_to_remove} endpoint'
        print(f"📝 Updated version from {old_version} to 2.0.0-modified")
    
    # Save modified version
    modified_path = Path("openmeteo-modified-v2.yml")
    with open(modified_path, "w", encoding='utf-8') as f:
        yaml.dump(modified_spec, f, default_flow_style=False, sort_keys=False)
    print(f"✅ Saved modified spec to {modified_path}")
    
    print("\n" + "="*60)
    print(f"🔴 Breaking change: Removed {endpoint_to_remove}")
    print(f"   Original had {len(spec['paths'])} endpoints")
    print(f"   Modified has {len(modified_spec['paths'])} endpoints")
    print("="*60)
    
    # Update serve_spec.py to serve the new file
    print(f"\n⚠️  Update serve_spec.py to serve: openmeteo-modified-v2.yml")
else:
    print("❌ No paths found in spec!")
