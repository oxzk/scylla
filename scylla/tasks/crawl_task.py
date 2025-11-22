"""Proxy crawl task module

Periodically crawls proxies from various sources using registered spiders.
"""

# Standard library imports
from datetime import datetime

# Local imports
from scylla import logger, c
from scylla.services.spider_service import spider_service
from scylla.services.proxy_service import proxy_service


async def crawl_task():
    """Execute proxy crawling from all configured spider sources.

    Fetches proxies from all registered spiders and saves them to the database.
    Logs statistics about the crawling operation including total fetched,
    successfully saved, and failed proxies.
    """
    try:
        start_time = datetime.now()

        results = await spider_service.run_all()

        # Process and save proxies
        total_proxies = 0
        saved_proxies = 0
        failed_proxies = 0

        for proxies in results:
            if not isinstance(proxies, list):
                continue

            total_proxies += len(proxies)
            saved_proxies += await proxy_service.add_batch(proxies)

        execution_time = (datetime.now() - start_time).total_seconds()

        logger.info(
            f"{c.GREEN}Proxy crawl completed{c.END} - "
            f"fetched {c.CYAN}{total_proxies}{c.END} proxies, "
            f"saved {c.PURPLE}{saved_proxies}{c.END}, "
            f"failed {c.RED}{failed_proxies}{c.END}, "
            f"time: {c.BLUE}{execution_time:.2f}s{c.END}"
        )
    except Exception as e:
        logger.error(f"Proxy crawl task failed: {e}", exc_info=True)
