from scylla.spiders.base import BaseSpider
from scylla.models import Proxy
from typing import List


class GetFreeProxySpider(BaseSpider):

    url_list = [
        "https://getfreeproxy.com/lists/socks4-proxy-list",
        "https://getfreeproxy.com/lists/socks5-proxy-list",
        "https://getfreeproxy.com/lists/http-proxy-list",
        "https://getfreeproxy.com/lists/https-proxy-list",
    ]
    status = True

    async def fetch_proxies(self) -> List[Proxy]:
        proxies = []
        for url in self.url_list:
            bs = await self.get_document(url)
            rows = bs.select("#proxy-table tbody tr")
            for row in rows:
                cols = [td.get_text(strip=True) for td in row.find_all("td")]
                if len(cols) < 5:
                    continue

                ip = cols[0]
                port = cols[1]
                protocol = cols[2]

                proxy_data = self.create_proxy_data(ip, port, protocol)
                if proxy_data:
                    proxies.append(proxy_data)

        return proxies
