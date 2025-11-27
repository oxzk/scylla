"""Pending/Failed proxy validation task module

Periodically validates pending or failed proxies (that haven't exceeded max failures)
to check if they are working.
"""

# Local imports
from scylla.core.config import settings
from scylla.services.proxy_service import proxy_service
from scylla.tasks.validate_base import execute_validation


async def validate_pending_task():
    """Execute batch proxy validation for pending/failed proxies.

    Fetches proxies that need validation (pending or failed but not exceeded
    max failures) from the database and validates them concurrently using batch
    validation. Updates the database with validation results including
    success/failure status and response times.
    """
    await execute_validation(
        proxy_iterator=proxy_service.get_proxies_needing_validation(
            settings.validate_batch_limit, settings.max_fail_count
        ),
        task_name="Pending proxy validation",
        no_proxies_message="No pending/failed proxies need validation",
    )
