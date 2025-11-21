from spiders.base import BaseSpider
from models import Proxy
from typing import List
from base64 import b64decode


class AdvancedSpider(BaseSpider):

    url_list = [f"https://advanced.name/freeproxy?page={i}" for i in range(1, 3)]

    async def fetch_proxies(self) -> List[Proxy]:
        proxies = []

        for url in self.url_list:
            bs = await self.get_document(url)
            rows = bs.select("#table_proxies tbody tr")
            for row in rows:
                ip_td = row.find("td", attrs={"data-ip": True})
                port_td = row.find("td", attrs={"data-port": True})
                protocol_tags = row.select("td a[href*='type']")
                country_tag = row.select_one("td a[href*='country']")

                ip = b64decode(ip_td["data-ip"]).decode("utf-8")
                port = b64decode(port_td["data-port"]).decode("utf-8")
                protocol = protocol_tags[0].get_text(strip=True).lower()
                country = (
                    country_tag.get_text(strip=True).upper() if country_tag else None
                )

                proxy_data = self.create_proxy_data(ip, port, protocol, country=country)
                if proxy_data:
                    proxies.append(proxy_data)

        return proxies
