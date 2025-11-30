"""Proxy Validator Service Module

Provides proxy validation functionality with support for HTTP/HTTPS/SOCKS4/SOCKS5
protocols using curl_cffi for better compatibility and performance.
"""

# Standard library imports
import asyncio
import time
from typing import Optional, List, Dict, Any

# Third-party imports
from curl_cffi import AsyncSession

# Local imports
from scylla import logger, c
from scylla.core.config import settings
from scylla.models import Proxy
from scylla.services.proxy_service import proxy_service


class ValidatorService:
    """Proxy validator with concurrent batch validation support.

    Uses curl_cffi's AsyncSession for proxy validation with support for all
    common proxy protocols. Implements semaphore-based concurrency control
    for efficient batch validation.

    Each batch validation creates its own session to avoid multi-worker conflicts.
    """

    def __init__(self):
        """Initialize validator with configuration from settings."""
        self.test_url = settings.proxy_test_url
        self.timeout = settings.proxy_test_timeout
        self.max_concurrent = settings.max_concurrent_validators

    def _detect_anonymity(self, headers: dict, proxy_ip: str) -> str:
        """Detect proxy anonymity level from response headers.

        Args:
            headers: Response headers dictionary
            proxy_ip: The proxy's IP address

        Returns:
            Anonymity level: 'transparent', 'anonymous', or 'elite'
        """
        headers_lower = {k.lower(): v for k, v in headers.items()}
        suspicious_headers = [
            "x-forwarded-for",
            "x-real-ip",
            "via",
            "x-proxy-id",
            "proxy-connection",
            "forwarded",
            "client-ip",
            "x-client-ip",
        ]

        # Check if proxy IP is exposed in any header
        for header_value in headers.values():
            if proxy_ip in str(header_value):
                return "transparent"

        # Check for proxy-revealing headers
        for header_name in suspicious_headers:
            if headers_lower.get(header_name):
                return "anonymous"

        return "elite"

    async def _validate_single(
        self,
        session: AsyncSession,
        proxy: Proxy,
        task_name: str = "",
    ) -> bool:
        """Validate a single proxy and update database immediately.

        Args:
            session: AsyncSession to use for the request
            proxy: Proxy object to validate
            task_name: Optional task name for logging context

        Returns:
            True if validation succeeded, False otherwise
        """

        if not proxy.id:
            return False

        url = self.test_url
        start_time = time.time()
        task_prefix = f"[{task_name}] " if task_name else ""

        is_success = False
        response_time = None
        anonymity = None

        try:
            response = await session.request(
                method="GET",
                url=url,
                proxy=proxy.url,
                timeout=self.timeout,
                verify=False,
                allow_redirects=True,
            )

            if response.ok:
                response_time = time.time() - start_time
                headers = dict(response.headers)
                origin = proxy.ip

                if url == "https://httpbin.org/get":
                    data = response.json()
                    headers = data.get("headers", {})
                    origin = data.get("origin", proxy.ip)

                anonymity = self._detect_anonymity(headers, origin)
                is_success = True

                logger.info(
                    f"{task_prefix}{c.GREEN}✓{c.END} {proxy.url} - "
                    f"speed: {response_time:.2f}s, anonymity: {c.CYAN}{anonymity}{c.END}"
                )
            else:
                logger.info(
                    f"{task_prefix}{c.RED}✗{c.END} {proxy.url} - status: {response.status_code}"
                )

        except asyncio.TimeoutError:
            logger.info(
                f"{task_prefix}{c.RED}✗{c.END} {proxy.url} - timeout after {self.timeout}s"
            )
        except Exception as e:
            logger.info(
                f"{task_prefix}{c.RED}✗{c.END} {proxy.url} - {type(e).__name__}"
            )

        # Update database immediately
        try:
            await proxy_service.record_validation_result(
                proxy.id, is_success, response_time, anonymity
            )
        except Exception as e:
            logger.error(f"Failed to update database for proxy {proxy.id}: {e}")
            return False

        return is_success

    async def validate_batch(
        self, proxies: List[Proxy], task_name: str = ""
    ) -> Dict[str, Any]:
        """Batch validate proxies with concurrent execution and immediate database updates.

        Creates a dedicated session for this batch to avoid multi-worker conflicts.
        Uses semaphore to control concurrency and prevent resource exhaustion.
        Database updates happen immediately within each validation.

        Args:
            proxies: List of proxies to validate
            task_name: Optional task name for logging context

        Returns:
            Dictionary with validation statistics:
                - total: Total number of proxies validated
                - success: Number of successful validations
                - failed: Number of failed validations
        """
        if not proxies:
            return {"total": 0, "success": 0, "failed": 0}

        semaphore = asyncio.Semaphore(self.max_concurrent)
        success_count = 0
        failed_count = 0

        async def validate_with_semaphore(session: AsyncSession, proxy: Proxy) -> bool:
            async with semaphore:
                return await self._validate_single(session, proxy, task_name)

        # Use dedicated session for this batch
        async with AsyncSession() as session:
            # Create all validation tasks
            tasks = [
                asyncio.create_task(validate_with_semaphore(session, proxy))
                for proxy in proxies
            ]

            # Wait for all tasks to complete and collect results
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Count statistics after all tasks complete
            for result in results:
                if isinstance(result, Exception):
                    failed_count += 1
                    logger.error(
                        f"Validation exception: {type(result).__name__}: {result}"
                    )
                elif result:
                    success_count += 1
                else:
                    failed_count += 1

        return {
            "total": len(proxies),
            "success": success_count,
            "failed": failed_count,
        }


# Global validator service instance
validator_service = ValidatorService()
