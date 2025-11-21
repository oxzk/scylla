from spiders.base import BaseSpider
from models import Proxy
from typing import List


class TomcatNycSpider(BaseSpider):

    url = "https://tomcat1235.nyc.mn/proxy_list"
    status = True

    async def fetch_proxies(self) -> List[Proxy]:
        proxies = []
        bs = await self.get_document(self.url)
        rows = bs.select("table tbody tr")
        for row in rows:
            cols = [td.get_text(strip=True) for td in row.find_all("td")]
            if len(cols) < 3:
                continue

            ip = cols[1]
            port = cols[2]
            protocol = cols[0]

            proxy_data = self.create_proxy_data(ip, port, protocol)
            if proxy_data:
                proxies.append(proxy_data)

        return proxies
