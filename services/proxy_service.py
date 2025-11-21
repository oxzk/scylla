from datetime import datetime, timedelta
from typing import List, Optional
from core.database import Database
from models.proxy import Proxy


class ProxyService:

    def __init__(self):
        self.db: Optional[Database] = None

    def init_db(self, db: Database):
        self.db = db

    async def add_proxy(self, proxy: Proxy) -> Optional[int]:
        query = """
        INSERT INTO proxies (ip, port, protocol, country, source, status)
        VALUES ($1, $2, $3, $4, $5, $6)
        ON CONFLICT (ip, port, protocol) DO NOTHING;
        """
        return await self.db.fetchval(
            query,
            proxy.ip,
            proxy.port,
            proxy.protocol,
            proxy.country,
            proxy.source,
            proxy.status,
        )

    async def update_proxy_validation(
        self,
        proxy_id: int,
        is_valid: bool,
        speed: Optional[float] = None,
        failure_count: int = 0,
    ):
        query = """
            UPDATE proxies 
            SET is_valid = $1, 
                speed = $2, 
                failure_count = $3,
                last_checked = $4,
                updated_at = $4
            WHERE id = $5
        """
        await db.execute(
            query, is_valid, speed, failure_count, datetime.now(), proxy_id
        )

    async def increment_failure_count(self, proxy_id: int):
        query = """
            UPDATE proxies 
            SET failure_count = failure_count + 1,
                last_checked = $1,
                updated_at = $1
            WHERE id = $2
        """
        await db.execute(query, datetime.now(), proxy_id)

    async def mark_invalid(self, proxy_id: int):
        query = """
            UPDATE proxies 
            SET is_valid = false,
                last_checked = $1,
                updated_at = $1
            WHERE id = $2
        """
        await db.execute(query, datetime.now(), proxy_id)

    async def get_valid_proxies(
        self,
        protocol: Optional[str] = None,
        country: Optional[str] = None,
        limit: int = 100,
    ) -> List[Proxy]:
        conditions = ["is_valid = true"]
        params = []
        param_count = 1

        if protocol:
            conditions.append(f"protocol = ${param_count}")
            params.append(protocol.lower())
            param_count += 1

        if country:
            conditions.append(f"country = ${param_count}")
            params.append(country.upper())
            param_count += 1

        where_clause = " AND ".join(conditions)

        query = f"""
            SELECT id, ip, port, protocol, country, anonymity, source, 
                   speed, is_valid, last_checked, failure_count, 
                   created_at, updated_at
            FROM proxies
            WHERE {where_clause}
            ORDER BY speed ASC NULLS LAST, last_checked DESC
            LIMIT ${param_count}
        """
        params.append(limit)

        rows = await db.fetch(query, *params)

        proxies = []
        for row in rows:
            proxy = Proxy(
                id=row["id"],
                ip=row["ip"],
                port=row["port"],
                protocol=row["protocol"],
                country=row["country"],
                anonymity=row["anonymity"],
                source=row["source"],
                speed=row["speed"],
                is_valid=row["is_valid"],
                last_checked=row["last_checked"],
                failure_count=row["failure_count"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )
            proxies.append(proxy)

        return proxies

    async def get_proxies_for_validation(self, limit: int = 100) -> List[Proxy]:
        query = """
            SELECT id, ip, port, protocol, country, anonymity, source, 
                   speed, is_valid, last_checked, failure_count, 
                   created_at, updated_at
            FROM proxies
            WHERE is_valid = true
            ORDER BY last_checked ASC NULLS FIRST
            LIMIT $1
        """

        rows = await db.fetch(query, limit)

        proxies = []
        for row in rows:
            proxy = Proxy(
                id=row["id"],
                ip=row["ip"],
                port=row["port"],
                protocol=row["protocol"],
                country=row["country"],
                anonymity=row["anonymity"],
                source=row["source"],
                speed=row["speed"],
                is_valid=row["is_valid"],
                last_checked=row["last_checked"],
                failure_count=row["failure_count"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )
            proxies.append(proxy)

        return proxies

    async def delete_invalid_proxies(self, max_failures: int = 3) -> int:
        query = """
            DELETE FROM proxies
            WHERE is_valid = false AND failure_count >= $1
        """
        result = await db.execute(query, max_failures)
        return int(result.split()[-1])

    async def delete_old_proxies(self, days: int = 7) -> int:
        cutoff_date = datetime.now() - timedelta(days=days)
        query = """
            DELETE FROM proxies
            WHERE last_checked < $1 OR (last_checked IS NULL AND created_at < $1)
        """
        result = await db.execute(query, cutoff_date)
        return int(result.split()[-1])

    async def get_stats(self) -> dict:
        query = """
            SELECT 
                COUNT(*) as total,
                COUNT(*) FILTER (WHERE is_valid = true) as valid,
                COUNT(*) FILTER (WHERE is_valid = false) as invalid,
                COUNT(DISTINCT protocol) as protocols,
                COUNT(DISTINCT country) as countries
            FROM proxies
        """
        row = await db.fetchrow(query)

        return {
            "total": row["total"],
            "valid": row["valid"],
            "invalid": row["invalid"],
            "protocols": row["protocols"],
            "countries": row["countries"],
        }


proxy_service = ProxyService()
