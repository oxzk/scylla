from spiders.base import BaseSpider
from models import Proxy
from typing import List


class FreeProxyWorldSpider(BaseSpider):

    url_list = [
        "https://www.freeproxy.world/?type=https&anonymity=&country=&speed=&port=&page=1",
        "https://www.freeproxy.world/?type=socks5&anonymity=&country=&speed=&port=&page=1",
    ]

    async def fetch_proxies(self) -> List[Proxy]:
        proxies = []
        for url in self.url_list:
            bs = await self.get_document(url)
            rows = bs.select(".layui-table tbody tr")
            for row in rows:
                cols = [td.get_text(strip=True) for td in row.find_all("td")]
                if len(cols) < 6:
                    continue

                ip = cols[0]
                port = cols[1]
                protocol = next((v for v in ["socks5", "https"] if v in cols[5]), None)

                proxy_data = self.create_proxy_data(ip, port, protocol)
                if proxy_data:
                    proxies.append(proxy_data)

        return proxies
