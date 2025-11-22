from scylla.spiders.base import BaseSpider
from scylla.models import Proxy
from typing import List


class FreeProxyListSpider(BaseSpider):

    url = "https://free-proxy-list.net/zh-cn/ssl-proxy.html"

    async def fetch_proxies(self) -> List[Proxy]:
        proxies = []
        bs = await self.get_document(self.url)
        rows = bs.select("#list table tbody tr")
        for row in rows:
            cols = [td.get_text(strip=True) for td in row.find_all("td")]
            if len(cols) < 7:
                continue

            ip = cols[0]
            port = int(cols[1])
            is_https = cols[6].lower() == "yes"
            protocol = "https" if is_https else "http"
            country = cols[2]

            proxy_data = self.create_proxy_data(ip, port, protocol, country=country)
            if proxy_data:
                proxies.append(proxy_data)

        return proxies
