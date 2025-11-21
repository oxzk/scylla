from spiders.base import BaseSpider
from models import Proxy
from typing import List


class GetFreeProxySpider(BaseSpider):

    url = "https://api.getfreeproxy.com/v1/proxies"

    async def fetch_proxies(self) -> List[Proxy]:
        proxies = []

        headers = {
            "Authorization": "Bearer 019aa51b83877e96add0bbab37ebbe1e",
            "Accept": "application/json",
        }

        for page in range(1, 21):
            params = {"protocol": "socks5", "page": page}
            response = await self.request(self.url, headers=headers, params=params)
            items = await response.json()
            for proxy in items:
                ip = proxy.get("ip")
                port = proxy.get("port")
                protocol = proxy.get("protocol")
                country = proxy.get("countryCode")

                proxy_data = self.create_proxy_data(ip, port, protocol, country=country)
                if proxy_data:
                    proxies.append(proxy_data)

        return proxies
