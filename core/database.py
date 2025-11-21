import asyncpg
from typing import Optional, List
from core.config import settings
from models import Proxy


class Database:
    def __init__(self):
        self.pool: Optional[asyncpg.Pool] = None

    async def connect(self):
        """创建数据库连接池"""
        self.pool = await asyncpg.create_pool(
            settings.db_url,
            min_size=settings.db_min_pool_size,
            max_size=settings.db_max_pool_size,
        )
        await self.init_tables()

    async def init_tables(self):
        CREATE_PROXY_TABLE = """
            CREATE TABLE IF NOT EXISTS proxies (
                id SERIAL PRIMARY KEY,
                ip VARCHAR(45) NOT NULL,
                port INTEGER NOT NULL,
                protocol VARCHAR(10) NOT NULL,
                country VARCHAR(2),
                anonymity VARCHAR(20),
                source VARCHAR(100) NOT NULL,
                speed FLOAT,
                success_count INTEGER DEFAULT 0,
                fail_count INTEGER DEFAULT 0,
                status INTEGER DEFAULT 0,
                last_checked TIMESTAMP,
                last_success TIMESTAMP,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(ip, port, protocol)
            );
            CREATE INDEX IF NOT EXISTS idx_proxies_country ON proxies(country);
            CREATE INDEX IF NOT EXISTS idx_proxies_protocol ON proxies(protocol);
            CREATE INDEX IF NOT EXISTS idx_proxies_status ON proxies(status);
            CREATE INDEX IF NOT EXISTS idx_proxies_fail_count ON proxies(fail_count);
            CREATE INDEX IF NOT EXISTS idx_proxies_last_success ON proxies(last_success);
            CREATE INDEX IF NOT EXISTS idx_proxies_quality ON proxies(success_count DESC, speed ASC);
        """
        async with self.pool.acquire() as conn:
            await conn.execute(CREATE_PROXY_TABLE)

    async def close(self):
        """关闭连接池"""
        if self.pool:
            await self.pool.close()

    async def execute(self, query: str, *args):
        async with self.pool.acquire() as conn:
            return await conn.execute(query, *args)

    async def fetch(self, query: str, *args):
        async with self.pool.acquire() as conn:
            return await conn.fetch(query, *args)

    async def fetchrow(self, query: str, *args):
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(query, *args)

    async def fetchval(self, query: str, *args):
        async with self.pool.acquire() as conn:
            return await conn.fetchval(query, *args)

    async def insert_proxy(self, proxy_data: Proxy):
        """插入或更新代理"""
        query = """
        INSERT INTO proxies (ip, port, protocol, country, source, status)
        VALUES ($1, $2, $3, $4, $5, 0)
        ON CONFLICT (ip, port, protocol) DO NOTHING;
        """
        async with self.pool.acquire() as conn:
            await conn.execute(
                query,
                proxy_data.ip,
                proxy_data.port,
                proxy_data.protocol,
                proxy_data.country,
                proxy_data.source,
            )

    async def get_proxies_for_validation(self, limit: int = 100) -> List[Proxy]:
        """获取需要验证的代理"""
        query = """
        SELECT *
        FROM proxies
        WHERE fail_count < $1 AND status = 'active'
        ORDER BY last_checked ASC NULLS FIRST
        LIMIT $2
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, config.max_fail_count, limit)
            return [self._row_to_model(row) for row in rows]

    async def update_proxy_validation(
        self, proxy_id: int, success: bool, speed: float = None
    ):
        """更新代理验证结果"""
        if success:
            query = """
            UPDATE proxies 
            SET success_count = success_count + 1,
                fail_count = 0,
                last_checked = NOW(),
                last_success = NOW(),
                speed = $2,
                status = 'active',
                updated_at = NOW()
            WHERE id = $1
            """
            async with self.pool.acquire() as conn:
                await conn.execute(query, proxy_id, speed)
        else:
            query = """
            UPDATE proxies 
            SET fail_count = fail_count + 1,
                last_checked = NOW(),
                status = CASE 
                    WHEN fail_count + 1 >= $2 THEN 'inactive'
                    ELSE status 
                END,
                updated_at = NOW()
            WHERE id = $1
            """
            async with self.pool.acquire() as conn:
                await conn.execute(query, proxy_id, config.max_fail_count)

    async def cleanup_invalid_proxies(self):
        """清理无效代理"""
        query = """
        DELETE FROM proxies 
        WHERE fail_count >= $1 
        OR (last_success IS NULL AND created_at < NOW() - INTERVAL '24 hours')
        OR last_success < NOW() - INTERVAL '7 days'
        OR status = 'inactive'
        """
        async with self.pool.acquire() as conn:
            result = await conn.execute(query, config.max_fail_count)
            return result

    async def get_available_proxies(
        self, protocol: str = None, country: str = None, limit: int = 10
    ) -> List[Proxy]:
        """获取可用代理"""
        conditions = [
            "fail_count < $1",
            "last_success IS NOT NULL",
            "status = 'active'",
        ]
        params = [config.max_fail_count]
        param_count = 1

        if protocol:
            param_count += 1
            conditions.append(f"protocol = ${param_count}")
            params.append(protocol)

        if country:
            param_count += 1
            conditions.append(f"country = ${param_count}")
            params.append(country.upper())

        param_count += 1
        params.append(limit)

        query = f"""
        SELECT *
        FROM proxies
        WHERE {' AND '.join(conditions)}
        ORDER BY 
            (success_count::float / NULLIF(success_count + fail_count, 0)) DESC,
            last_success DESC,
            speed ASC NULLS LAST
        LIMIT ${param_count}
        """

        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, *params)
            return [self._row_to_model(row) for row in rows]

    def _row_to_model(self, row) -> Proxy:
        """将数据库行转换为Proxy"""
        return Proxy(
            id=row["id"],
            ip=row["ip"],
            port=row["port"],
            protocol=row["protocol"],
            country=row["country"],
            anonymity=row["anonymity"],
            source=row["source"],
            speed=row["speed"],
            success_count=row["success_count"],
            fail_count=row["fail_count"],
            status=row["status"],
            last_checked=row["last_checked"],
            last_success=row["last_success"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    async def get_proxy_by_id(self, proxy_id: int) -> Optional[Proxy]:
        """根据ID获取代理"""
        query = "SELECT * FROM proxies WHERE id = $1"
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, proxy_id)
            return self._row_to_model(row) if row else None

    async def get_stats(self) -> dict:
        """获取统计信息"""
        async with self.pool.acquire() as conn:
            # 总代理数
            total = await conn.fetchval("SELECT COUNT(*) FROM proxies")

            # 可用代理数
            available = await conn.fetchval(
                "SELECT COUNT(*) FROM proxies WHERE fail_count < $1 AND last_success IS NOT NULL AND status = 'active'",
                config.max_fail_count,
            )

            # 按协议分组
            by_protocol = await conn.fetch(
                "SELECT protocol, COUNT(*) as count FROM proxies WHERE status = 'active' GROUP BY protocol"
            )

            # 按国家分组
            by_country = await conn.fetch(
                """SELECT country, COUNT(*) as count 
                FROM proxies 
                WHERE status = 'active' AND country IS NOT NULL 
                GROUP BY country 
                ORDER BY count DESC 
                LIMIT 10"""
            )

            # 平均速度
            avg_speed = await conn.fetchval(
                "SELECT AVG(speed) FROM proxies WHERE speed IS NOT NULL AND status = 'active'"
            )

            return {
                "total": total,
                "available": available,
                "by_protocol": {row["protocol"]: row["count"] for row in by_protocol},
                "top_countries": {row["country"]: row["count"] for row in by_country},
                "average_speed": round(float(avg_speed), 2) if avg_speed else None,
            }


db = Database()
