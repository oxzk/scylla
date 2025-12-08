"""Proxy Validator Service Module

Provides proxy validation functionality with support for HTTP/HTTPS/SOCKS4/SOCKS5
protocols using curl_cffi for better compatibility and performance.
"""

# Standard library imports
import asyncio
import time
from typing import Optional, List, Dict, Any, Tuple

# Third-party imports
from curl_cffi import AsyncSession

# Local imports
from scylla import logger, c
from scylla.core.config import settings
from scylla.models import Proxy


# Type alias for validation result
ValidationResult = Tuple[int, bool, Optional[float], Optional[str]]


class ValidatorService:
    """Proxy validator with concurrent batch validation support.

    Uses curl_cffi's AsyncSession for proxy validation with support for all
    common proxy protocols. Implements semaphore-based concurrency control
    for efficient batch validation.

    Each batch validation creates its own session to avoid multi-worker conflicts.
    """

    # Suspicious headers that may reveal proxy usage
    SUSPICIOUS_HEADERS = [
        "x-forwarded-for",
        "x-real-ip",
        "via",
        "x-proxy-id",
        "proxy-connection",
        "forwarded",
        "client-ip",
        "x-client-ip",
    ]

    def __init__(self):
        """Initialize validator with configuration from settings."""
        self.test_url = settings.validator_test_url
        self.timeout = settings.validator_timeout
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

        # Check if proxy IP is exposed in any header value
        for header_value in headers.values():
            if proxy_ip in str(header_value):
                return "transparent"

        # Check for proxy-revealing headers
        for header_name in self.SUSPICIOUS_HEADERS:
            if headers_lower.get(header_name):
                return "anonymous"

        return "elite"

    async def _validate_single(
        self,
        session: AsyncSession,
        proxy: Proxy,
    ) -> ValidationResult:
        """Validate a single proxy and return validation result.

        Args:
            session: AsyncSession to use for the request
            proxy: Proxy object to validate

        Returns:
            Tuple of (proxy_id, success, response_time, anonymity):
                - proxy_id: ID of the validated proxy (0 if no ID)
                - success: Whether validation succeeded
                - response_time: Response time in seconds (None if failed)
                - anonymity: Anonymity level (transparent/anonymous/elite, None if failed)
        """
        if not proxy.id:
            return (0, False, None, None)

        # Use country-specific test URL for CN proxies
        test_url = self.test_url
        if proxy.country and proxy.country.upper() == "CN":
            test_url = "http://connect.rom.miui.com/generate_204"

        start_time = time.time()
        success = False
        response_time = None
        anonymity = None

        try:
            response = await session.request(
                method="GET",
                url=test_url,
                proxy=proxy.url,
                timeout=self.timeout,
                verify=False,
                allow_redirects=True,
            )

            if response.ok:
                response_time = time.time() - start_time
                headers = dict(response.headers)

                anonymity = self._detect_anonymity(headers, proxy.ip)
                success = True

                logger.info(
                    f"{c.GREEN}✓{c.END} {proxy.url} - "
                    f"speed: {response_time:.2f}s, anonymity: {c.CYAN}{anonymity}{c.END}"
                )
            else:
                logger.info(
                    f"{c.RED}✗{c.END} {proxy.url} - status: {response.status_code}"
                )

        except asyncio.TimeoutError:
            logger.info(f"{c.RED}✗{c.END} {proxy.url} - timeout after {self.timeout}s")
        except Exception as e:
            logger.info(f"{c.RED}✗{c.END} {proxy.url} - {type(e).__name__}")

        return (proxy.id, success, response_time, anonymity)

    async def validate_batch(self, proxies: List[Proxy]) -> Dict[str, Any]:
        """Batch validate proxies with concurrent execution.

        Creates a dedicated session for this batch to avoid multi-worker conflicts.
        Uses semaphore to control concurrency and prevent resource exhaustion.
        Returns validation results without performing database updates.

        Args:
            proxies: List of proxies to validate

        Returns:
            Dictionary with validation statistics and results:
                - total: Total number of proxies validated
                - success: Number of successful validations
                - failed: Number of failed validations
                - results: List of (proxy_id, success, response_time, anonymity) tuples
        """
        if not proxies:
            return {"total": 0, "success": 0, "failed": 0, "results": []}

        semaphore = asyncio.Semaphore(self.max_concurrent)

        async def validate_with_semaphore(session: AsyncSession, proxy: Proxy):
            async with semaphore:
                return await self._validate_single(session, proxy)

        # Use dedicated session for this batch
        async with AsyncSession() as session:
            tasks = [
                asyncio.create_task(validate_with_semaphore(session, proxy))
                for proxy in proxies
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

        # Process results
        success_count = 0
        failed_count = 0
        validation_results = []

        for result in results:
            if isinstance(result, Exception):
                failed_count += 1
                logger.error(f"Validation exception: {type(result).__name__}")
                continue

            if isinstance(result, tuple) and len(result) == 4:
                proxy_id, success, response_time, anonymity = result
                validation_results.append((proxy_id, success, response_time, anonymity))

                if success:
                    success_count += 1
                else:
                    failed_count += 1

        return {
            "total": len(proxies),
            "success": success_count,
            "failed": failed_count,
            "results": validation_results,
        }


# Global validator service instance
validator_service = ValidatorService()
