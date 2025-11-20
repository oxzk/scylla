from abc import ABC, abstractmethod
from typing import List, Optional
from models import ProxyData, ProxyProtocol
from pydantic import ValidationError
from aiohttp import ClientSession, ClientResponse
from bs4 import BeautifulSoup
import asyncio
import logging


class BaseSpider(ABC):
    """爬虫基类"""

    def __init__(
        self,
        name: Optional[str] = None,
        request_session: Optional[ClientSession] = None,
    ):
        self.name = name or self.__class__.__name__
        self.session = request_session
        self.user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36 Edg/136.0.0.0"
        self.logger = logging.getLogger("sanic.access")

    @property
    def current_request_session(self) -> ClientSession:
        if self.session is None:
            self.session = ClientSession()
        return self.session

    async def close_session(self):
        """关闭HTTP会话"""
        if self.session:
            await self.session.close()
            self.session = None

    @abstractmethod
    async def fetch_proxies(self) -> List[ProxyData]:
        """
        抓取代理列表
        返回格式: List[ProxyData]
        """
        pass

    def create_proxy_data(
        self, ip: str, port: int, protocol: str, **kwargs
    ) -> ProxyData:
        try:
            return ProxyData(
                ip=ip,
                port=port,
                protocol=ProxyProtocol(protocol.lower()),
                source=self.name,
                **kwargs,
            )
        except (ValidationError, ValueError) as e:
            self.logger.error(f"[{self.name}] 创建代理数据失败: {e}")
            return None

    async def run(self):
        """运行爬虫"""
        try:
            proxies = await self.fetch_proxies()

            # 保存到数据库
            saved_count = 0
            for proxy in proxies:
                self.logger.info(f"[{self.name}] 代理 {proxy.ip}:{proxy.port} 已获取")
                try:
                    # await db.insert_proxy(proxy)
                    saved_count += 1
                except Exception as e:
                    self.logger.error(
                        f"[{self.name}] 保存代理失败 {proxy.ip}:{proxy.port} - {e}"
                    )

            return saved_count
        except Exception as e:
            self.logger.error(f"[{self.name}] 爬取失败1: {e}", exc_info=True)
            return 0
        finally:
            await self.close_session()

    async def request(
        self,
        url: str,
        method: str = "GET",
        **request_kwargs,
    ) -> ClientResponse:

        headers = request_kwargs.pop("headers", {})
        headers.setdefault("user-agent", self.user_agent)

        timeout = int(request_kwargs.pop("timeout", 15))

        request_kwargs.setdefault("headers", headers)
        request_kwargs.setdefault("timeout", timeout)
        request_kwargs.setdefault("verify_ssl", False)

        return await asyncio.wait_for(
            self.current_request_session.request(method, url, **request_kwargs),
            timeout=timeout,
        )

    async def get_html(self, url: str, **request_kwargs) -> BeautifulSoup:
        response = await self.request(url, **request_kwargs)
        html = await response.text()
        return BeautifulSoup(html, "html.parser")
