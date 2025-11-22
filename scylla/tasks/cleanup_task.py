"""Proxy cleanup task module

Periodically cleans up failed and stale proxies from the database.
"""

# Standard library imports
from datetime import datetime

# Local imports
from scylla import logger, c
from scylla.services.proxy_service import proxy_service


async def cleanup_task():
    """Execute cleanup of failed and stale proxies.

    Removes proxies that have exceeded the failure threshold and proxies
    that haven't been successful for an extended period.
    """
    try:
        start_time = datetime.now()

        # Clean up failed proxies (fail_count >= 3)
        failed_deleted = await proxy_service.cleanup_failed_proxies(max_failures=3)

        # Clean up stale proxies (no success in 7 days)
        stale_deleted = await proxy_service.cleanup_stale_proxies(days=7)

        total_deleted = failed_deleted + stale_deleted
        execution_time = (datetime.now() - start_time).total_seconds()

        if total_deleted > 0:
            logger.info(
                f"{c.GREEN}Cleanup completed{c.END} - "
                f"removed {c.RED}{failed_deleted}{c.END} failed proxies, "
                f"{c.YELLOW}{stale_deleted}{c.END} stale proxies, "
                f"total: {c.CYAN}{total_deleted}{c.END}, "
                f"time: {c.BLUE}{execution_time:.2f}s{c.END}"
            )
        else:
            logger.info(
                f"{c.GREEN}Cleanup completed{c.END} - "
                f"no proxies removed, "
                f"time: {c.BLUE}{execution_time:.2f}s{c.END}"
            )

    except Exception as e:
        logger.error(f"Proxy cleanup task failed: {e}", exc_info=True)
