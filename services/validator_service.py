import asyncio
import aiohttp
from aiohttp_socks import ProxyConnector, ProxyType as SocksProxyType
import time
from typing import Tuple, Optional
from core.config import config
from core.database import db
from models import ProxyModel, ProxyProtocol


class ProxyValidator:
    """代理验证器 - 支持HTTP/HTTPS/SOCKS4/SOCKS5"""

    def __init__(self):
        self.http_test_urls = config.validate_urls
        self.socks_test_url = config.socks5_test_url
        self.http_timeout = config.validate_timeout
        self.socks_timeout = config.socks5_timeout

    async def validate_proxy(
        self, proxy: ProxyModel
    ) -> Tuple[int, bool, Optional[float]]:
        """
        验证单个代理
        返回: (proxy_id, success, speed)
        """
        if proxy.protocol in [ProxyProtocol.SOCKS4, ProxyProtocol.SOCKS5]:
            return await self._validate_socks_proxy(proxy)
        else:
            return await self._validate_http_proxy(proxy)

    async def _validate_http_proxy(
        self, proxy: ProxyModel
    ) -> Tuple[int, bool, Optional[float]]:
        """验证HTTP/HTTPS代理"""
        proxy_url = proxy.url

        # 尝试多个测试URL
        for test_url in self.http_test_urls:
            try:
                start_time = time.time()
                timeout = aiohttp.ClientTimeout(total=self.http_timeout)

                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.get(
                        test_url, proxy=proxy_url, ssl=False, allow_redirects=True
                    ) as response:
                        if response.status == 200:
                            # 验证响应内容
                            await response.text()
                            speed = time.time() - start_time
                            return (proxy.id, True, speed)
            except asyncio.TimeoutError:
                continue
            except aiohttp.ClientProxyConnectionError:
                continue
            except aiohttp.ClientError:
                continue
            except Exception as e:
                continue

        return (proxy.id, False, None)

    async def _validate_socks_proxy(
        self, proxy: ProxyModel
    ) -> Tuple[int, bool, Optional[float]]:
        """验证SOCKS4/SOCKS5代理"""
        try:
            # 确定SOCKS类型
            if proxy.protocol == ProxyProtocol.SOCKS4:
                proxy_type = SocksProxyType.SOCKS4
            elif proxy.protocol == ProxyProtocol.SOCKS5:
                proxy_type = SocksProxyType.SOCKS5
            else:
                return (proxy.id, False, None)

            start_time = time.time()

            # 创建SOCKS代理连接器
            connector = ProxyConnector(
                proxy_type=proxy_type, host=proxy.ip, port=proxy.port, rdns=True
            )

            timeout = aiohttp.ClientTimeout(total=self.socks_timeout)

            async with aiohttp.ClientSession(
                connector=connector, timeout=timeout
            ) as session:
                async with session.get(self.socks_test_url, ssl=False) as response:
                    if response.status == 200:
                        # 读取响应以确保连接完全建立
                        await response.text()
                        speed = time.time() - start_time
                        return (proxy.id, True, speed)

        except asyncio.TimeoutError:
            pass
        except Exception as e:
            # 记录SOCKS特定错误
            if "authentication" in str(e).lower():
                print(f"[SOCKS] 代理 {proxy.ip}:{proxy.port} 需要认证")
            pass

        return (proxy.id, False, None)

    async def validate_batch(self, proxies: list):
        """批量验证代理"""
        if not proxies:
            print("没有需要验证的代理")
            return 0

        print(f"开始验证 {len(proxies)} 个代理...")

        # 统计各类型代理数量
        protocol_counts = {}
        for proxy in proxies:
            protocol = proxy.protocol
            protocol_counts[protocol] = protocol_counts.get(protocol, 0) + 1

        print(f"代理类型分布: {protocol_counts}")

        semaphore = asyncio.Semaphore(config.max_concurrent_validators)

        async def validate_with_semaphore(proxy):
            async with semaphore:
                return await self.validate_proxy(proxy)

        results = await asyncio.gather(
            *[validate_with_semaphore(proxy) for proxy in proxies],
            return_exceptions=True,
        )

        # 更新数据库
        success_count = 0
        protocol_success = {}

        for result in results:
            if isinstance(result, tuple):
                proxy_id, success, speed = result
                await db.update_proxy_validation(proxy_id, success, speed)
                if success:
                    success_count += 1
                    # 找到对应的代理以统计协议
                    for proxy in proxies:
                        if proxy.id == proxy_id:
                            protocol = proxy.protocol
                            protocol_success[protocol] = (
                                protocol_success.get(protocol, 0) + 1
                            )
                            break

        print(f"验证完成: {success_count}/{len(proxies)} 个代理可用")
        print(f"各协议可用数: {protocol_success}")
        return success_count

    async def validate_single_url(self, proxy: ProxyModel, test_url: str) -> bool:
        """使用指定URL验证单个代理"""
        try:
            if proxy.protocol in [ProxyProtocol.SOCKS4, ProxyProtocol.SOCKS5]:
                proxy_type = (
                    SocksProxyType.SOCKS5
                    if proxy.protocol == ProxyProtocol.SOCKS5
                    else SocksProxyType.SOCKS4
                )
                connector = ProxyConnector(
                    proxy_type=proxy_type, host=proxy.ip, port=proxy.port
                )
                async with aiohttp.ClientSession(connector=connector) as session:
                    async with session.get(
                        test_url, timeout=aiohttp.ClientTimeout(total=10)
                    ) as response:
                        return response.status == 200
            else:
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        test_url,
                        proxy=proxy.url,
                        timeout=aiohttp.ClientTimeout(total=10),
                    ) as response:
                        return response.status == 200
        except Exception:
            return False


# 全局验证器实例
validator = ProxyValidator()
