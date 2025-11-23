"""Proxy validation task module

Periodically validates proxies in the database to ensure they are still working.
"""

# Standard library imports
from datetime import datetime

# Local imports
from scylla import logger, c
from scylla.core.config import settings
from scylla.services.proxy_service import proxy_service
from scylla.services.validator_service import validator_service


async def validate_task():
    """Execute batch proxy validation for proxies needing validation.

    Fetches proxies that need validation from the database and validates them
    concurrently using batch validation. Updates the database with validation
    results including success/failure status and response times.
    """
    try:
        start_time = datetime.now()

        # Get proxies needing validation
        proxies = [
            p async for p in proxy_service.get_proxies_needing_validation(300, settings.max_fail_count)
        ]

        if not proxies:
            logger.info(f"{c.YELLOW}No proxies need validation{c.END}")
            return

        logger.info(
            f"{c.CYAN}Starting batch validation for {len(proxies)} proxies{c.END}"
        )

        # Batch validate proxies with concurrent execution
        stats = await validator_service.validate_batch(proxies)

        # Update database with validation results
        for proxy_id, is_success, response_time, anonymity in stats["results"]:
            if proxy_id:
                await proxy_service.record_validation_result(
                    proxy_id=proxy_id,
                    is_success=is_success,
                    response_time=response_time,
                    anonymity=anonymity,
                )

        execution_time = (datetime.now() - start_time).total_seconds()
        logger.info(
            f"{c.GREEN}Validation completed{c.END} - "
            f"success: {c.GREEN}{stats['success']}{c.END}, "
            f"failed: {c.RED}{stats['failed']}{c.END}, "
            f"total: {c.CYAN}{stats['total']}{c.END}, "
            f"time: {c.BLUE}{execution_time:.2f}s{c.END}"
        )
    except Exception as e:
        logger.error(f"Proxy validation task failed: {e}", exc_info=True)
    finally:
        await validator_service.close()
