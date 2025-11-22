"""Proxy Validator Service Module

Provides proxy validation functionality with support for HTTP/HTTPS/SOCKS4/SOCKS5
protocols using curl_cffi for better compatibility and performance.
"""

# Standard library imports
import asyncio
import time
from typing import Tuple, Optional, List, Dict, Any

# Third-party imports
from curl_cffi import AsyncSession

# Local imports
from scylla import logger, c
from scylla.core.config import settings
from scylla.models import Proxy


class ValidatorService:
    """Proxy validator with concurrent batch validation support.

    Uses curl_cffi's AsyncSession for proxy validation with support for all
    common proxy protocols. Implements semaphore-based concurrency control
    for efficient batch validation.

    Attributes:
        test_url: URL used for proxy validation
        timeout: Request timeout in seconds
        max_concurrent: Maximum concurrent validations
    """

    def __init__(self):
        """Initialize validator with configuration from settings."""
        self.test_url = settings.proxy_test_url
        self.timeout = settings.proxy_test_timeout
        self.max_concurrent = settings.max_concurrent_validators
        self._session: Optional[AsyncSession] = None

    @property
    def current_session(self) -> AsyncSession:
        """Get or create shared AsyncSession with lazy initialization.

        Returns:
            AsyncSession instance for making requests
        """
        if self._session is None:
            self._session = AsyncSession()
        return self._session

    async def close(self) -> None:
        """Close AsyncSession and cleanup resources."""
        if self._session is not None:
            await self._session.close()
            self._session = None

    async def validate_proxy(
        self, proxy: Proxy, test_url: Optional[str] = None
    ) -> Tuple[int, bool, Optional[float], Optional[str]]:
        """Validate a single proxy by making a test request.

        Args:
            proxy: Proxy object to validate
            test_url: Optional test URL, defaults to configured URL

        Returns:
            Tuple of (proxy_id, success, response_time, anonymity):
                - proxy_id: ID of the validated proxy (0 if no ID)
                - success: Whether validation succeeded
                - response_time: Response time in seconds (None if failed)
                - anonymity: Anonymity level (transparent/anonymous/elite, None if failed)
        """
        if not proxy.id:
            logger.warning(f"Proxy {proxy.url} has no ID, skipping validation")
            return (0, False, None, None)

        url = test_url or self.test_url
        proxy_url = proxy.url
        start_time = time.time()

        try:
            # Make request through proxy
            response = await self.current_session.request(
                method="GET",
                url=url,
                proxy=proxy_url,
                timeout=self.timeout,
                verify=False,  # Skip SSL verification for proxy compatibility
                allow_redirects=True,
            )

            # Validate response
            if response.ok:
                # Read content to ensure full connection
                _ = response.text
                response_time = time.time() - start_time

                # Detect anonymity level from response headers
                anonymity = self._detect_anonymity(response.headers, proxy.ip)

                logger.info(
                    f"{c.GREEN}✓{c.END} Proxy {proxy.source} {proxy.url} validated successfully, "
                    f"speed: {response_time:.2f}s, anonymity: {c.CYAN}{anonymity}{c.END}"
                )
                return (proxy.id, True, response_time, anonymity)
            else:
                logger.info(
                    f"{c.RED}✗{c.END} Proxy {proxy.source} {proxy.url} returned status {response.status_code}"
                )
                return (proxy.id, False, None, None)

        except asyncio.TimeoutError:
            logger.info(
                f"{c.RED}✗{c.END} Proxy {proxy.source} {proxy.url} timed out after {self.timeout}s"
            )
            return (proxy.id, False, None, None)
        except Exception as e:
            logger.info(
                f"{c.RED}✗{c.END} Proxy {proxy.source} {proxy.url} validation failed: {type(e).__name__}"
            )
            return (proxy.id, False, None, None)

    def _detect_anonymity(self, headers: dict, proxy_ip: str) -> str:
        """Detect proxy anonymity level from response headers.

        Args:
            headers: Response headers from the test request
            proxy_ip: IP address of the proxy being tested

        Returns:
            Anonymity level: 'transparent', 'anonymous', or 'elite'
        """
        # Headers that indicate real IP exposure (check first for transparency)
        ip_exposure_headers = ["x-forwarded-for", "x-real-ip", "client-ip", "forwarded"]

        # Check if real IP is exposed (transparent proxy)
        for header_name in ip_exposure_headers:
            # Check both lowercase and title case
            header_value = headers.get(header_name) or headers.get(header_name.title())
            if header_value:
                # If the header contains an IP different from proxy IP, it's transparent
                if proxy_ip.lower() not in header_value.lower():
                    return "transparent"

        # Headers that indicate proxy usage
        proxy_indicator_headers = [
            "via",
            "x-proxy-id",
            "x-proxy",
            "proxy-connection",
            "x-forwarded",
            "forwarded-for",
        ]

        # Check if any proxy headers exist (anonymous proxy)
        for header_name in proxy_indicator_headers:
            if header_name in headers or header_name.title() in headers:
                return "anonymous"

        # No proxy-related headers found (elite proxy)
        return "elite"

    async def validate_batch(self, proxies: List[Proxy]) -> Dict[str, Any]:
        """Batch validate proxies with concurrent execution.

        Uses semaphore to control concurrency and prevent resource exhaustion.
        All proxies are validated concurrently up to max_concurrent limit.

        Args:
            proxies: List of proxies to validate

        Returns:
            Dictionary with validation statistics:
                - total: Total number of proxies validated
                - success: Number of successful validations
                - failed: Number of failed validations
                - results: List of (proxy_id, success, speed, anonymity) tuples
        """
        if not proxies:
            return {"total": 0, "success": 0, "failed": 0, "results": []}

        # Semaphore for concurrency control
        semaphore = asyncio.Semaphore(self.max_concurrent)

        async def validate_with_semaphore(
            proxy: Proxy,
        ) -> Tuple[int, bool, Optional[float], Optional[str]]:
            """Validate proxy with semaphore protection."""
            async with semaphore:
                return await self.validate_proxy(proxy)

        # Execute all validations concurrently
        results = await asyncio.gather(
            *[validate_with_semaphore(proxy) for proxy in proxies],
            return_exceptions=True,
        )

        # Process results and collect statistics
        success_count = 0
        failed_count = 0
        validation_results = []

        for result in results:
            if isinstance(result, Exception):
                # Exception during validation
                failed_count += 1
                logger.error(f"Validation exception: {type(result).__name__}")
                continue

            if isinstance(result, tuple) and len(result) == 4:
                proxy_id, success, speed, anonymity = result
                validation_results.append((proxy_id, success, speed, anonymity))

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
