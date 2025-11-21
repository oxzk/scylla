from abc import ABC, abstractmethod
from typing import List, Optional
from models import Proxy
from pydantic import ValidationError
from aiohttp import ClientSession, ClientResponse
from bs4 import BeautifulSoup
import asyncio
import logging


class BaseSpider(ABC):
    """Base class for all proxy spiders

    Attributes:
        status: Whether the spider is enabled (default: False)
        name: Spider name, defaults to class name without 'Spider' suffix
    """

    status: bool = False
    name: Optional[str] = None

    def __init__(
        self,
        request_session: Optional[ClientSession] = None,
    ):
        """Initialize the spider

        Args:
            request_session: Optional existing aiohttp ClientSession to reuse
        """
        if not self.name:
            self.name = self.__class__.__name__.replace("Spider", "")
        self.session = request_session
        self.user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36 Edg/136.0.0.0"
        self.logger = logging.getLogger("sanic.access")

    @property
    def current_request_session(self) -> ClientSession:
        """Get or create HTTP session (lazy initialization)"""
        if self.session is None:
            self.session = ClientSession()
        return self.session

    async def close_session(self):
        """Close HTTP session and cleanup resources"""
        if self.session:
            await self.session.close()
            self.session = None

    @abstractmethod
    async def fetch_proxies(self) -> List[Proxy]:
        """Fetch proxy list from the source

        This method must be implemented by all spider subclasses.

        Returns:
            List of Proxy objects
        """
        pass

    def create_proxy_data(
        self, ip: str, port: int, protocol: str, country: Optional[str] = None, **kwargs
    ) -> Optional[Proxy]:
        """Create a Proxy object with validation

        Args:
            ip: IP address
            port: Port number
            protocol: Protocol type (http, https, socks4, socks5)
            country: Country code (ISO 3166-1 alpha-2, e.g., 'US', 'CN')
            **kwargs: Additional proxy attributes (anonymity, speed, etc.)

        Returns:
            Proxy object if validation succeeds, None otherwise
        """
        try:
            return Proxy(
                ip=ip,
                port=port,
                protocol=protocol,
                country=country,
                source=self.name,
                **kwargs,
            )
        except (ValidationError, ValueError) as e:
            self.logger.warning(
                f"[{self.name}] Proxy validation failed: {protocol}://{ip}:{port} {country} - {e}"
            )
            return None

    async def run(self) -> List[Proxy]:
        """Execute the spider and fetch proxies

        Returns:
            List of successfully fetched and validated Proxy objects
        """
        try:
            return await self.fetch_proxies()
        finally:
            await self.close_session()

    async def request(
        self,
        url: str,
        method: str = "GET",
        **request_kwargs,
    ) -> ClientResponse:
        """Make an HTTP request with timeout control

        Args:
            url: Target URL
            method: HTTP method (default: GET)
            **request_kwargs: Additional arguments for aiohttp request

        Returns:
            aiohttp ClientResponse object

        Raises:
            asyncio.TimeoutError: If request exceeds timeout
        """
        headers = request_kwargs.pop("headers", {})
        headers.setdefault("user-agent", self.user_agent)

        timeout = request_kwargs.pop("timeout", 20)

        request_kwargs["headers"] = headers
        request_kwargs["timeout"] = timeout
        request_kwargs.setdefault("verify_ssl", False)

        return await asyncio.wait_for(
            self.current_request_session.request(method, url, **request_kwargs),
            timeout=timeout,
        )

    async def get_document(self, url: str, **request_kwargs) -> BeautifulSoup:
        """Fetch and parse HTML document

        Args:
            url: Target URL
            **request_kwargs: Additional arguments for request method

        Returns:
            BeautifulSoup object for HTML parsing
        """
        response = await self.request(url, **request_kwargs)
        html = await response.text()
        return BeautifulSoup(html, "html.parser")
