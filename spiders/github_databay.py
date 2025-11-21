from spiders.base import BaseSpider
from models import Proxy
from typing import List


class GithubDataBaySpider(BaseSpider):

    url_list = {
        "https": "https://cdn.jsdelivr.net/gh/databay-labs/free-proxy-list/https.txt",
        "http": "https://cdn.jsdelivr.net/gh/databay-labs/free-proxy-list/http.txt",
        "socks5": "https://cdn.jsdelivr.net/gh/databay-labs/free-proxy-list/socks5.txt",
    }

    async def fetch_proxies(self) -> List[Proxy]:
        proxies = []

        for protocol, url in self.url_list.items():
            response = await self.request(url)
            html = await response.text()
            items = html.split("\n")
            for item in items:
                if ":" not in item:
                    continue

                proxy = item.split(":")
                ip = proxy[0]
                port = proxy[1]

                proxy_data = self.create_proxy_data(ip, port, protocol)
                if proxy_data:
                    proxies.append(proxy_data)

        return proxies
