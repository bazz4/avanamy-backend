#!/usr/bin/env python3
"""
Cron script to poll all active watched APIs.

Usage:
    python scripts/poll_watched_apis.py

Add to crontab to run automatically:
    # Run every hour
    0 * * * * cd /path/to/avanamy-backend && python scripts/poll_watched_apis.py

    # Run every day at 2am
    0 2 * * * cd /path/to/avanamy-backend && python scripts/poll_watched_apis.py
"""

import asyncio
import sys
import logging
from pathlib import Path

# Add src to path so we can import avanamy
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from avanamy.db.database import SessionLocal
from avanamy.services.polling_service import poll_all_active_apis

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('poll_watched_apis.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)


async def main():
    """Main polling function."""
    logger.info("=" * 80)
    logger.info("Starting scheduled poll of watched APIs")
    logger.info("=" * 80)
    
    db = SessionLocal()
    
    try:
        results = await poll_all_active_apis(db)
        
        logger.info("Polling results:")
        logger.info(f"  Total APIs: {results['total']}")
        logger.info(f"  Successful: {results['success']}")
        logger.info(f"  No changes: {results['no_change']}")
        logger.info(f"  Errors: {results['errors']}")
        logger.info(f"  Versions created: {results['versions_created']}")
        
        if results['errors'] > 0:
            logger.warning(f"{results['errors']} APIs failed to poll")
            sys.exit(1)  # Non-zero exit code for monitoring
        
    except Exception as e:
        logger.exception("Fatal error during polling")
        sys.exit(1)
    
    finally:
        db.close()
    
    logger.info("Polling complete")
    logger.info("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())