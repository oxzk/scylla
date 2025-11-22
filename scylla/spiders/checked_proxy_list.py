from scylla.spiders.base import BaseSpider
from scylla.models import Proxy
from typing import List
import json


class CheckedProxyListSpider(BaseSpider):

    url_list = [
        "https://raw.githubusercontent.com/ClearProxy/checked-proxy-list/main/socks5/json/all.json",
        "https://raw.githubusercontent.com/ClearProxy/checked-proxy-list/main/socks4/json/all.json",
        "https://raw.githubusercontent.com/ClearProxy/checked-proxy-list/main/http/json/all.json",
    ]

    async def fetch_proxies(self) -> List[Proxy]:
        proxies = []

        for url in self.url_list:
            response = await self.request(url)
            html = await response.text()
            items = json.loads(html)
            for proxy in items:
                ip = proxy.get("ip")
                port = proxy.get("port")
                protocol = proxy.get("protocol")
                country = proxy.get("country_code")

                proxy_data = self.create_proxy_data(ip, port, protocol, country=country)
                if proxy_data:
                    proxies.append(proxy_data)

        return proxies
