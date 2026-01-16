#!/usr/bin/env python3
"""
Test script for manual polling flow with breaking change detection and auto-scan triggering.

This tests the complete flow:
1. Serve spec locally
2. Manual poll detects changes
3. Breaking changes trigger impact analysis
4. Affected repos are scheduled for immediate scanning

Usage:
    python scripts/test_manual_poll.py
"""

import asyncio
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta
import subprocess
import time
import requests
import os

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

if "pytest" in sys.modules:
    import pytest
    pytest.skip("Manual polling script is not a pytest test.", allow_module_level=True)

from dotenv import load_dotenv
load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env")

from avanamy.db.database import SessionLocal
from avanamy.models.watched_api import WatchedAPI
from avanamy.models.api_product import ApiProduct
from avanamy.models.provider import Provider
from avanamy.models.code_repository import CodeRepository
from avanamy.services.polling_service import PollingService

# Test configuration
SPEC_FILE = Path(__file__).parent / "openmeteo-modified-v2.yml"
SPEC_PORT = 5001
SPEC_URL = f"http://localhost:{SPEC_PORT}/openmeteo-modified-v2.yml"


def serve_spec():
    """Start a simple HTTP server to serve the test spec."""
    print(f"\n🌐 Starting HTTP server on port {SPEC_PORT}...")
    print(f"   Serving: {SPEC_FILE}")
    
    # Start server in background
    server = subprocess.Popen(
        ["python", "-m", "http.server", str(SPEC_PORT)],
        cwd=SPEC_FILE.parent,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    
    # Wait for server to start
    time.sleep(2)
    
    # Verify server is running
    try:
        response = requests.get(f"http://localhost:{SPEC_PORT}/")
        print(f"   ✓ Server running (status: {response.status_code})")
    except Exception as e:
        print(f"   ✗ Server failed to start: {e}")
        server.kill()
        return None
    
    return server


async def test_manual_poll():
    """Test the complete manual polling flow."""
    
    print("=" * 80)
    print("TESTING MANUAL POLL WITH BREAKING CHANGES & AUTO-SCAN")
    print("=" * 80)
    
    # Start spec server
    server = serve_spec()
    if not server:
        print("❌ Failed to start spec server")
        return False
    
    try:
        db = SessionLocal()
        
        # Step 1: Find active watched API
        print("\n📋 Step 1: Setting up test watched API...")
        
        # Find first active watched API
        watched_api = db.query(WatchedAPI).filter(
            WatchedAPI.polling_enabled == True
        ).first()
        
        if not watched_api:
            print("   ⚠ No active watched APIs found")
            print("   Please create one in the UI first, then run this test")
            return False
        
        # Get the API product name for display
        api_product = db.query(ApiProduct).filter(
            ApiProduct.id == watched_api.api_product_id
        ).first()
        
        product_name = api_product.name if api_product else "Unknown"
        
        print(f"   Using watched API: {product_name}")
        print(f"   Tenant ID: {watched_api.tenant_id}")
        print(f"   Current spec URL: {watched_api.spec_url}")
        
        # Update spec URL to local server
        old_url = watched_api.spec_url
        watched_api.spec_url = SPEC_URL
        db.commit()
        print(f"   ✓ Updated spec URL to: {SPEC_URL}")
        
        # Step 2: Check repositories that might be affected
        print("\n📦 Step 2: Checking repositories...")
        
        repos = db.query(CodeRepository).filter(
            CodeRepository.tenant_id == watched_api.tenant_id
        ).all()
        
        print(f"   Found {len(repos)} repositories for tenant")
        
        if len(repos) == 0:
            print("   ⚠ No repositories found - impact analysis won't trigger scans")
        else:
            # Set all repos to scan far in future (so we can see auto-trigger)
            for repo in repos:
                repo.next_scan_at = datetime.now(timezone.utc) + timedelta(days=7)
                print(f"   - {repo.name}: scan scheduled for 7 days from now")
            db.commit()
            print("   ✓ Reset all repo scan times")
        
        # Step 3: Trigger manual poll
        print("\n🔄 Step 3: Triggering manual poll...")
        print(f"   Polling: {product_name}")
        print(f"   URL: {SPEC_URL}")
        
        polling_service = PollingService(db)
        result = await polling_service.poll_watched_api(watched_api.id)
        
        print("\n   Poll results:")
        print(f"   Status: {result.get('status')}")
        print(f"   Message: {result.get('message')}")
        
        if result.get('status') == 'error':
            print(f"   ❌ Error: {result.get('error')}")
            return False
        
        if result.get('status') == 'no_change':
            print("   ℹ No changes detected")
            print("   This is expected if you've already polled this spec before")
            print("   To test breaking changes:")
            print("   1. Modify openmeteo-modified-v2.yml")
            print("   2. Or change the spec URL to openmeteo-original.yml")
            print("   3. Run poll again")
            return True
        
        # Step 4: Check if breaking changes were detected
        print("\n🔍 Step 4: Checking for breaking changes...")
        
        if result.get('version_created'):
            version_number = result.get('version_number')
            print(f"   ✓ New version created: v{version_number}")
            
            # Check version history for breaking changes
            from avanamy.models.version_history import VersionHistory
            version = db.query(VersionHistory).filter(
                VersionHistory.api_spec_id == watched_api.api_spec_id,
                VersionHistory.version == version_number
            ).first()
            
            if version and version.diff:
                is_breaking = version.diff.get("breaking", False)
                changes = version.diff.get("changes", [])
                
                print(f"   Breaking changes: {is_breaking}")
                print(f"   Total changes: {len(changes)}")
                
                if is_breaking:
                    print("\n   🚨 Breaking changes detected!")
                    for i, change in enumerate(changes[:5], 1):  # Show first 5
                        print(f"      {i}. {change.get('type', 'unknown')}: {change.get('path', 'N/A')}")
                    
                    if len(changes) > 5:
                        print(f"      ... and {len(changes) - 5} more")
                
        # Step 5: Check if repos were scheduled for scanning
        print("\n🔬 Step 5: Checking if repos were auto-scheduled for scanning...")
        
        db.refresh(watched_api)  # Refresh to get latest data
        
        now = datetime.now(timezone.utc)
        repos_needing_scan = db.query(CodeRepository).filter(
            CodeRepository.tenant_id == watched_api.tenant_id,
            CodeRepository.next_scan_at <= now
        ).all()
        
        if len(repos_needing_scan) > 0:
            print(f"   ✓ {len(repos_needing_scan)} repos scheduled for immediate scanning!")
            for repo in repos_needing_scan:
                print(f"      - {repo.name}: next_scan_at = {repo.next_scan_at}")
            print("\n   🎉 AUTO-SCAN TRIGGERING WORKS!")
        else:
            print("   ℹ No repos scheduled for immediate scanning")
            print("   This could mean:")
            print("   - No breaking changes detected")
            print("   - No affected code usages found")
            print("   - Impact analysis didn't run")
        
        # Step 6: Restore original URL
        print("\n🔧 Step 6: Cleanup...")
        watched_api.spec_url = old_url
        db.commit()
        print(f"   ✓ Restored original spec URL")
        
        print("\n" + "=" * 80)
        print("✅ MANUAL POLL TEST COMPLETE")
        print("=" * 80)
        
        return True
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False
        
    finally:
        # Stop server
        if server:
            print("\n🛑 Stopping HTTP server...")
            server.kill()
            server.wait()
        
        db.close()


if __name__ == "__main__":
    success = asyncio.run(test_manual_poll())
    sys.exit(0 if success else 1)
