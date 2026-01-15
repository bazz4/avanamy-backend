"""
Background script to automatically scan code repositories on schedule.

Similar to poll_watched_apis.py, this runs periodically to:
1. Find repositories that need scanning (next_scan_at <= now)
2. Trigger GitHub repo scans
3. Update scan status and schedule next scan

Usage:
    python scripts/scan_code_repositories.py

Set SCAN_DRY_RUN=1 to see what would be scanned without actually scanning.
"""

import asyncio
import os
import sys
from pathlib import Path
from datetime import datetime, timedelta, timezone
import logging
from dotenv import load_dotenv
load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env")

# Add src to path so we can import avanamy modules
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from sqlalchemy import select
from sqlalchemy.orm import Session

from avanamy.db.database import get_db

from avanamy.models.code_repository import CodeRepository
from avanamy.services.github_app_service import GitHubAppService  
from avanamy.services.code_repo_scanner_service import CodeRepoScannerService
from avanamy.logging_config import configure_logging

configure_logging()
logger = logging.getLogger(__name__)

DRY_RUN = os.getenv("SCAN_DRY_RUN", "0") == "1"


async def scan_repository(db: Session, repo: CodeRepository) -> bool:
    """
    Scan a single code repository.
    
    Args:
        db: Database session
        repo: CodeRepository to scan
        
    Returns:
        True if scan succeeded, False if failed
    """
    logger.info(f"Scanning repository: {repo.name} (id={repo.id})")
    
    if DRY_RUN:
        logger.info(f"[DRY RUN] Would scan repository: {repo.name}")
        return True
    
    # Check if we have GitHub App installation FIRST
    if not repo.github_installation_id:
        logger.warning(f"⚠ Repository {repo.name} has no GitHub App installation - skipping")
        return False
    
    try:
        # Get installation token
        app_service = GitHubAppService()
        installation_token = await app_service.get_installation_token(
            repo.github_installation_id
        )
        
        # Scan the repository
        scanner_service = CodeRepoScannerService(db)
        await scanner_service.scan_repository_from_github(
            code_repository_id=repo.id,
            access_token=installation_token
        )
        
        logger.info(
            f"✓ Scan completed: {repo.name} - "
            f"Found {repo.total_endpoints_found} endpoints in "
            f"{repo.total_files_scanned} files"
        )
        return True
            
    except Exception as e:
        logger.exception(f"✗ Exception scanning {repo.name}: {e}")
        return False


async def process_repository_scans():
    """
    Main function to find and scan repositories that need scanning.
    """
    logger.info("=" * 80)
    logger.info("Starting repository scan job")
    logger.info(f"DRY_RUN: {DRY_RUN}")
    logger.info("=" * 80)
    
    db_gen = get_db()
    db: Session = next(db_gen)
    
    try:
        # Find repositories that need scanning
        now = datetime.now(timezone.utc)
        
        repos_to_scan = db.execute(
            select(CodeRepository)
            .where(CodeRepository.next_scan_at <= now)
            .where(CodeRepository.scan_status != "scanning")  # Don't re-scan if already in progress
            .order_by(CodeRepository.next_scan_at)
        ).scalars().all()
        
        logger.info(f"Found {len(repos_to_scan)} repositories to scan")
        
        if len(repos_to_scan) == 0:
            logger.info("No repositories need scanning at this time")
            return
        
        # Process each repository
        success_count = 0
        failure_count = 0
        
        for repo in repos_to_scan:
            logger.info(f"\n--- Repository: {repo.name} ---")
            logger.info(f"  Last scanned: {repo.last_scanned_at or 'Never'}")
            logger.info(f"  Next scan scheduled: {repo.next_scan_at}")
            logger.info(f"  Scan interval: {repo.scan_interval_hours} hours")
            logger.info(f"  Consecutive failures: {repo.consecutive_scan_failures}")
            
            # Update status to 'scanning' if not dry run
            if not DRY_RUN:
                repo.scan_status = "scanning"
                db.commit()
            
            # Perform the scan
            scan_succeeded = await scan_repository(db, repo)
            
            if not DRY_RUN:
                if scan_succeeded:
                    # Success: reset failure count, schedule next scan
                    repo.consecutive_scan_failures = 0
                    repo.scan_status = "completed"
                    repo.last_scanned_at = datetime.now(timezone.utc)
                    repo.next_scan_at = datetime.now(timezone.utc) + timedelta(hours=repo.scan_interval_hours)
                    success_count += 1
                    
                    logger.info(f"✓ Successfully scanned {repo.name}")
                    logger.info(f"  Next scan scheduled: {repo.next_scan_at}")
                else:
                    # Failure: increment failure count, exponential backoff
                    repo.consecutive_scan_failures += 1
                    repo.scan_status = "failed"
                    
                    # Exponential backoff: 1hr, 2hr, 4hr, 8hr, then back to normal interval
                    if repo.consecutive_scan_failures <= 4:
                        backoff_hours = 2 ** (repo.consecutive_scan_failures - 1)
                        repo.next_scan_at = datetime.now(timezone.utc) + timedelta(hours=backoff_hours)
                        logger.warning(
                            f"✗ Scan failed for {repo.name}. "
                            f"Failure #{repo.consecutive_scan_failures}. "
                            f"Retrying in {backoff_hours} hour(s)"
                        )
                    else:
                        # After 4 failures, go back to normal schedule
                        repo.next_scan_at = datetime.now(timezone.utc) + timedelta(hours=repo.scan_interval_hours)
                        logger.warning(
                            f"✗ Scan failed for {repo.name}. "
                            f"Max retries exceeded. Back to normal schedule."
                        )
                    
                    failure_count += 1
                
                db.commit()
                db.refresh(repo)
        
        # Summary
        logger.info("\n" + "=" * 80)
        logger.info("Repository scan job complete")
        logger.info(f"Total repositories processed: {len(repos_to_scan)}")
        logger.info(f"Successful scans: {success_count}")
        logger.info(f"Failed scans: {failure_count}")
        logger.info("=" * 80)
        
    except Exception as e:
        logger.exception(f"Error in repository scan job: {e}")
        raise
    finally:
        try:
            next(db_gen)
        except StopIteration:
            pass


def main():
    """Entry point for the script."""
    try:
        asyncio.run(process_repository_scans())
    except KeyboardInterrupt:
        logger.info("\nInterrupted by user")
    except Exception as e:
        logger.exception(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()