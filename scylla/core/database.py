# Third-party imports
import asyncpg
from typing import Optional, List

# Local imports
from scylla.core.config import settings
from scylla.models import Proxy
from scylla import CREATE_PROXY_TABLE


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


db = Database()
