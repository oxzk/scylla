"""Base validation task module

Provides shared validation logic for both pending and successful proxy validation tasks.
"""

# Standard library imports
from datetime import datetime
from typing import AsyncIterator

# Local imports
from scylla import logger, c
from scylla.models.proxy import Proxy
from scylla.services.proxy_service import proxy_service
from scylla.services.validator_service import validator_service


async def execute_validation(
    proxy_iterator: AsyncIterator[Proxy],
    task_name: str,
    no_proxies_message: str,
) -> None:
    """Execute batch proxy validation with shared logic.

    Args:
        proxy_iterator: Async iterator yielding proxies to validate
        task_name: Name of the validation task for logging
        no_proxies_message: Message to log when no proxies are found
    """
    try:
        start_time = datetime.now()

        # Collect proxies from iterator
        proxies = [p async for p in proxy_iterator]

        if not proxies:
            logger.info(f"{c.YELLOW}{no_proxies_message}{c.END}")
            return

        logger.info(f"{c.CYAN}Starting {task_name} for {len(proxies)} proxies{c.END}")

        # Batch validate proxies with concurrent execution
        stats = await validator_service.validate_batch(proxies)

        # Update database for each validation result
        for proxy_id, is_success, response_time, anonymity in stats["results"]:
            if proxy_id == 0:
                continue
            try:
                await proxy_service.record_validation_result(
                    proxy_id, is_success, response_time, anonymity
                )
            except Exception as e:
                logger.error(f"Failed to update database for proxy {proxy_id}: {e}")

        execution_time = (datetime.now() - start_time).total_seconds()
        logger.info(
            f"{c.GREEN}{task_name} completed{c.END} - "
            f"success: {c.GREEN}{stats['success']}{c.END}, "
            f"failed: {c.RED}{stats['failed']}{c.END}, "
            f"total: {c.CYAN}{stats['total']}{c.END}, "
            f"time: {c.BLUE}{execution_time:.2f}s{c.END}"
        )
    except Exception as e:
        logger.error(f"{task_name} failed: {e}", exc_info=True)
