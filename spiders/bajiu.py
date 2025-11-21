from spiders.base import BaseSpider
from models import Proxy
from typing import List


class BaJiuSpider(BaseSpider):

    url_list = [
        "https://www.89ip.cn/",
        "https://www.89ip.cn/index_2.html",
    ]
    status = True

    async def fetch_proxies(self) -> List[Proxy]:
        proxies = []

        for url in self.url_list:
            bs = await self.get_document(url)
            rows = bs.select(".layui-table tbody tr")
            for row in rows:
                cols = [td.get_text(strip=True) for td in row.find_all("td")]
                if len(cols) < 4:
                    continue

                ip = cols[0]
                port = int(cols[1])
                protocol = "http"
                country = "CN"

                proxy_data = self.create_proxy_data(ip, port, protocol, country=country)
                if proxy_data:
                    proxies.append(proxy_data)

        return proxies
