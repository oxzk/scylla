# Third-party imports
import asyncpg
from typing import Optional, List

# Local imports
from scylla.core.config import settings
from scylla.models import Proxy
from scylla import CREATE_PROXY_TABLE, logger


class Database:
    def __init__(self):
        self.pool: Optional[asyncpg.Pool] = None

    async def connect(self):
        """Create database connection pool with initialization."""
        if self.pool is not None:
            logger.debug("Database already connected, skipping")
            return

        try:
            self.pool = await asyncpg.create_pool(
                settings.db_url,
                min_size=settings.db_min_pool_size,
                max_size=settings.db_max_pool_size,
            )
            await self.init_tables()
            logger.debug("✓ Database connection pool created")
        except Exception as e:
            logger.error(f"Failed to connect to database: {e}", exc_info=True)
            raise

    async def init_tables(self):
        """Initialize database tables."""
        async with self.pool.acquire() as conn:
            await conn.execute(CREATE_PROXY_TABLE)

    async def close(self):
        """Close database connection pool gracefully."""
        if self.pool:
            try:
                await self.pool.close()
                logger.debug("✓ Database connection pool closed")
            except Exception as e:
                logger.error(f"Error closing database pool: {e}")
            finally:
                self.pool = None

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
