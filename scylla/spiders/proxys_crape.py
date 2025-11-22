from scylla.spiders.base import BaseSpider
from scylla.models import Proxy
from typing import List


class ProxyScrapeSpider(BaseSpider):

    url = "https://api.proxyscrape.com/v3/free-proxy-list/get?request=displayproxies&proxy_format=protocolipport&format=json&limit=100"

    async def fetch_proxies(self) -> List[Proxy]:
        proxies = []
        response = await self.request(self.url)
        result = await response.json()
        for proxy in result.get("proxies", []):
            ip = proxy.get("ip")
            port = proxy.get("port")
            protocol = proxy.get("protocol")
            country = proxy.get("ip_data", {}).get("countryCode")

            proxy_data = self.create_proxy_data(ip, port, protocol, country=country)
            if proxy_data:
                proxies.append(proxy_data)

        return proxies
