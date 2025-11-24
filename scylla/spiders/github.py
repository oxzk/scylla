from scylla.spiders.base import BaseSpider
from scylla.models import Proxy
from typing import List


class GithubSpider(BaseSpider):

    data_map = {
        "GithubVakhov": {
            "https": "https://vakhov.github.io/fresh-proxy-list/https.txt",
            "http": "https://vakhov.github.io/fresh-proxy-list/http.txt",
            "socks5": "https://vakhov.github.io/fresh-proxy-list/socks5.txt",
            "socks4": "https://vakhov.github.io/fresh-proxy-list/socks4.txt",
        },
        "GithubIplocate": {
            "https": "https://raw.githubusercontent.com/iplocate/free-proxy-list/main/protocols/protocols/http.txt",
            "http": "https://raw.githubusercontent.com/iplocate/free-proxy-list/main/protocols/https.txt",
            "socks5": "https://raw.githubusercontent.com/iplocate/free-proxy-list/main/protocols/socks5.txt",
            "socks4": "https://raw.githubusercontent.com/iplocate/free-proxy-list/main/protocols/socks4.txt",
        },
        "GithubDataBay": {
            "https": "https://cdn.jsdelivr.net/gh/databay-labs/free-proxy-list/https.txt",
            "http": "https://cdn.jsdelivr.net/gh/databay-labs/free-proxy-list/http.txt",
            "socks5": "https://cdn.jsdelivr.net/gh/databay-labs/free-proxy-list/socks5.txt",
        },
        "GithubR00tee": {
            "http": "https://raw.githubusercontent.com/r00tee/Proxy-List/main/Https.txt",
            "socks5": "https://raw.githubusercontent.com/r00tee/Proxy-List/main/Socks5.txt",
            "socks4": "https://raw.githubusercontent.com/r00tee/Proxy-List/main/Socks4.txt",
        },
    }
    status = True

    async def fetch_proxies(self) -> List[Proxy]:
        proxies = []

        for name, url_list in self.data_map.items():
            self.name = name
            for protocol, url in url_list.items():
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
