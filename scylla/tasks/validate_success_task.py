"""Successful proxy validation task module

Periodically re-validates successful proxies to ensure they remain working.
"""

# Local imports
from scylla.services.proxy_service import proxy_service
from scylla.tasks.validate_base import execute_validation


async def validate_success_task():
    """Execute batch proxy validation for successful proxies.

    Fetches proxies that have been successful and re-validates them to ensure
    they are still working. This helps maintain the quality of the proxy pool
    by detecting when previously successful proxies become unavailable.
    """
    await execute_validation(
        proxy_iterator=proxy_service.get_successful_proxies_for_validation(),
        task_name="Success proxy validation",
        no_proxies_message="No successful proxies need validation",
    )
